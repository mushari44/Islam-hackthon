"""Build data/corpus/qa.jsonl from two Q&A encyclopedias in icadb (icadb.com).

icadb is the central content database of the Islamic Content Service
Association (the publisher of QuranEnc and HadeethEnc), which the challenge's
scholarly package lists as an approved source. Two of its encyclopedias answer
exactly the questions Sabeeli gets:
  110  موسوعة الأسئلة والأجوبة لغير المسلمين  (questions and doubts from non-Muslims)
  102  موسوعة الأسئلة والأجوبة للمسلمين       (questions a new Muslim asks)
The export endpoint is public and returns approved versions only. The text is
Arabic; the API carries no translations for these cards yet.

Each Q&A item stays one unit (never chunked), so a citation always points to a
complete answer a reader can check on islamenc.com, the association's public
viewer for the same cards.

Verses quoted inside an answer (﴿...﴾) are matched word by word against the
Mushaf and replaced by [[q:SURA:AYA]] markers, so the verse text the user sees
always comes from the reference Mushaf, as everywhere else in Sabeeli. A verse
that doesn't match exactly is left as the source wrote it and listed in the
report, for a human to look at.

Raw API responses are cached in data/raw/icadb/ (git-ignored).

Usage:  python scripts/ingest_icadb.py [--refresh]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.core.textnorm import normalize_ar, skeleton  # noqa: E402
from backend.app.features.rag.corpus import get_corpus  # noqa: E402
from backend.app.features.rag.quran_match import get_matcher  # noqa: E402

RAW = ROOT / "data" / "raw" / "icadb"
OUT = ROOT / "data" / "corpus" / "qa.jsonl"
REPORT = RAW / "report.json"

API = "https://icadb.com/api/encyclopedias/{enc}/cards/latest/?page={page}&page_size=1000"
VIEWER = "https://islamenc.com/ar/enc-cards/{enc}/card/{card}"
ENCYCLOPEDIAS = {
    110: {"ar": "موسوعة الأسئلة والأجوبة لغير المسلمين", "en": "Q&A Encyclopedia for Non-Muslims", "category_table": 18},
    102: {"ar": "موسوعة الأسئلة والأجوبة للمسلمين", "en": "Q&A Encyclopedia for Muslims", "category_table": 11},
}

VERSE_RE = re.compile(r"﴿([^﴾]{3,4000})﴾")
# the sura/aya reference the source writes after a verse, e.g. "[الأعراف ٥٤]." (the card shows it instead)
REF_AFTER_RE = re.compile(r"^\s*[\[(][^\])\n]{2,60}[٠-٩0-9][^\])\n]{0,20}[\])]\.?")
AYA_NUM_RE = re.compile(r"[٠-٩0-9]+")
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def fetch(enc: int, refresh: bool) -> list[dict]:
    path = RAW / f"enc_{enc}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))["cards"]
    cards, page = [], 1
    with httpx.Client(headers={"User-Agent": "Sabeeli-ingest"}, timeout=120) as client:
        while True:
            r = client.get(API.format(enc=enc, page=page))
            r.raise_for_status()
            data = r.json()
            cards += data["cards"]
            if page >= int(data.get("total_pages") or 1):
                break
            page += 1
    RAW.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"cards": cards}, ensure_ascii=False), encoding="utf-8")
    return cards


@lru_cache(maxsize=1)
def _verses_by_aya() -> dict[int, list[tuple[str, int, str]]]:
    """aya number -> [(id, sura, letter skeleton)] for every verse of the Mushaf."""
    out: dict[int, list[tuple[str, int, str]]] = defaultdict(list)
    for p in get_corpus().passages.values():
        if p.kind == "quran":
            out[p.data["aya"]].append((p.id, p.data["sura"], skeleton(p.data["text_ar"])))
    return out


@lru_cache(maxsize=1)
def _sura_names() -> tuple[set[str], list[str]]:
    """Normalised sura names: one-word names (matched as whole words) and longer ones (matched as text)."""
    names = {normalize_ar(p.data["sura_name_ar"]) for p in get_corpus().passages.values() if p.kind == "quran"}
    names |= {n[2:] for n in names if n.startswith("ال")}
    return {n for n in names if " " not in n}, [n for n in names if " " in n]


def _is_sura_ref(ref: str) -> bool:
    """True for "[الأعراف ٥٤]" or "[سورة البروج: 16]"; False for a hadith source such as "[صحيح مسلم (2647)]".

    Only a sura reference is dropped after a verse (the verse card shows the right one, even where
    the source's own reference is wrong); any other bracket stays in the text.
    """
    norm = normalize_ar(ref)
    words, phrases = _sura_names()
    toks = set(re.findall(r"\w+", norm))
    return bool(toks & ({"سوره", "سورة"} | words)) or any(p in norm for p in phrases)


def _fits(piece_sk: str, verse_sk: str) -> bool:
    """The same letters as the verse, or (for a longer excerpt written with "...") a contiguous part of it."""
    return piece_sk == verse_sk or (len(piece_sk) >= 8 and piece_sk in verse_sk)


def _candidates(piece: str, num: int | None) -> list[list[str]]:
    sk = skeleton(piece)
    if not sk:
        return []
    if num:  # the source gave the aya number: check every verse with that number
        return [[vid] for vid, _, vsk in _verses_by_aya().get(num, []) if _fits(sk, vsk)]
    corpus = get_corpus()
    out = []
    for m in get_matcher().match(piece, max_results=20):
        ref_sk = "".join(skeleton(corpus.get(i).data["text_ar"]) for i in m.ids)
        if m.score == 1.0 and _fits(sk, ref_sk):
            out.append(m.ids)
    return out


def verse_markers(span: str) -> list[str] | None:
    """Mushaf ids for a quoted span, or None unless every verse in it is identified with certainty.

    The source numbers each verse ("...طِينٖ ١٢ ثُمَّ..."), so the span is split there and each
    piece is identified on its own, by its letters and its aya number. A piece that fits several
    verses (a phrase repeated in the Quran) is settled by the sura of its neighbours in the span.
    """
    parts = AYA_NUM_RE.split(span)
    nums = AYA_NUM_RE.findall(span)
    pieces = []
    for k, text in enumerate(parts):
        if text.strip(" \n.…"):
            num = nums[k] if k < len(nums) else None
            pieces.append((text, int(num.translate(DIGITS)) if num else None))
    if not pieces:
        return None
    options = [_candidates(text, num) for text, num in pieces]
    suras = {opts[0][0].split(":")[1] for opts in options if len(opts) == 1}
    ids: list[str] = []
    for opts in options:
        if len(opts) > 1 and len(suras) == 1:
            opts = [o for o in opts if o[0].split(":")[1] in suras]
        if len(opts) != 1:
            return None
        ids += [i for i in opts[0] if i not in ids]
    return ids


def replace_verses(text: str, report: list[dict], card_id: str) -> tuple[str, list[str]]:
    refs: list[str] = []
    out, pos = [], 0
    for m in VERSE_RE.finditer(text):
        ids = verse_markers(m.group(1))
        out.append(text[pos:m.start()])
        pos = m.end()
        if ids is None:
            report.append({"card": card_id, "span": m.group(1)[:160]})
            out.append(m.group(0))
            continue
        refs += [i for i in ids if i not in refs]
        out.append("\n" + "\n".join(f"[[{i}]]" for i in ids) + "\n")
        ref = REF_AFTER_RE.match(text[pos:])
        if ref and _is_sura_ref(ref.group(0)):
            pos += ref.end()
    out.append(text[pos:])
    clean = re.sub(r"[ \t]+\n", "\n", "".join(out))
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return clean, refs


def field(card: dict, *names: str) -> str:
    for s in card.get("sentences") or []:
        if s["field_name"] in names:
            text = (s.get("text") or "").strip()
            return "" if text == "--" else text
    return ""


def build(refresh: bool) -> None:
    rows, report = [], []
    for enc, meta in ENCYCLOPEDIAS.items():
        cards = fetch(enc, refresh)
        kept = 0
        for c in cards:
            ver = c.get("latest_version") or {}
            if not ver.get("is_approved", True):
                continue
            question = field(c, "السؤال")
            answer = field(c, "الجواب")
            if not answer:
                continue
            pid = f"qa:{c['external_id']}"
            answer, refs = replace_verses(answer, report, pid)
            categories = [it["name"] for it in c.get("lookup_items") or []
                          if it.get("lookup_table_external_id") == meta["category_table"]]
            rows.append({
                "id": pid, "card": c["external_id"], "version": ver.get("version_str") or "",
                "enc": enc, "enc_ar": meta["ar"], "enc_en": meta["en"],
                "title": field(c, "العنوان") or question, "question": question or field(c, "العنوان"),
                "answer": answer, "refs": refs, "categories": categories, "section": field(c, "المصدر"),
                "url_ar": VIEWER.format(enc=enc, card=c["external_id"]),
            })
            kept += 1
        print(f"encyclopedia {enc}: {kept} of {len(cards)} cards")
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    replaced = sum(len(r["refs"]) for r in rows)
    print(f"wrote {len(rows)} Q&A items to {OUT.relative_to(ROOT)}; {replaced} verse references from the Mushaf, "
          f"{len(report)} quoted spans left as written (see {REPORT.relative_to(ROOT)})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="download again instead of using data/raw/icadb")
    build(ap.parse_args().refresh)
