"""Build data/corpus/bayyinat.jsonl from «بينات: أسئلة وأجوبة عن الإسلام».

The challenge's scholarly package (page 4) names this book as the primary
source for doubts and recurring questions, at dawa.center/file/7937. The book
is a 1,259-page PDF with 263 questions, each laid out the same way: the
question, similar wordings of it, the gist of the question, a short answer and
a detailed answer.

The PDF is typeset for print, so its text layer needs repair before use:
  * every line is rebuilt from glyph positions (right to left), which fixes
    reversed ligatures (اإلسالم -> الإسلام, اهلل -> الله), spaces drawn on top of
    a letter (نقضُ ها -> نقضُها) and punctuation that the layout moved;
  * Quran verses are set in the King Fahd Complex page fonts (QCF), whose
    glyphs carry no text. Each verse is followed by its reference, e.g.
    [يس: 40], so the verse becomes a [[q:36:40]] marker and the app shows it
    from the Mushaf. A verse with no reference next to it becomes ﴿…﴾.

The book's rights are reserved by its publisher, so the PDF (data/raw/) and
the extracted text (data/corpus/bayyinat.jsonl) are git-ignored: each copy of
Sabeeli builds them locally from the package's own link with this script.

Usage:  python scripts/ingest_bayyinat.py
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.core.textnorm import normalize_ar  # noqa: E402
from backend.app.features.rag.corpus import get_corpus  # noqa: E402

RAW = ROOT / "data" / "raw" / "bayyinat"
PDF = RAW / "bayyinat.pdf"
OUT = ROOT / "data" / "corpus" / "bayyinat.jsonl"
REPORT = RAW / "report.json"
PACKAGE_URL = "https://dawa.center/file/7937"   # the link given in the challenge's package

VERSE = "￼"
LTR_RUN = re.compile(r"[0-9٠-٩A-Za-z][0-9٠-٩A-Za-z.,/%\-]*[0-9٠-٩A-Za-z]|[0-9٠-٩]")
TOC_ITEM = re.compile(r"^\((\d{1,3})\)\s*[-:]?\s*(.+?)\s*\.{3,}\s*\d+$")
TOC_TAIL = re.compile(r"^(.+?)\s*\.{3,}\s*\d+$")
MAIN_SECTION = re.compile(r"^((?:أول|ثاني|ثالث|رابع|خامس|سادس|سابع|ثامن|تاسع|عاشر|حادي عشر|ثاني عشر)\S*)\s*:\s*(.+?)\s*\.{3,}\s*\d+$")
HEADING_NUM = re.compile(r"[()](\d{1,3})[()]")
REF = re.compile(r"^\s*[،,.]?\s*\[\s*(?:سورة\s+)?([^\]:\d٠-٩]{1,30}?)\s*:\s*([\d٠-٩]{1,3})(?:\s*[-–]\s*([\d٠-٩]{1,3}))?\s*\]")
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

LABELS = {normalize_ar(k): v for k, v in {
    "السؤال": "question", "عبارات مشابهة للسؤال": "similar", "الجواب": "answer",
    "مضمون السؤال": "gist", "مختصر الإجابة": "short", "الجواب التفصيلي": "detailed"}.items()}


# ---- download ----------------------------------------------------------------

def download() -> None:
    """Fetch the PDF that the package's page links to."""
    if PDF.exists():
        return
    RAW.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=300, headers={"User-Agent": "Sabeeli-ingest"}) as client:
        page = client.get(PACKAGE_URL).text
        m = re.search(r"https://dawa\.center/storage/files/[A-Za-z0-9]+\.pdf", page)
        if not m:
            sys.exit(f"no PDF link found on {PACKAGE_URL}")
        with client.stream("GET", m.group(0)) as r:
            r.raise_for_status()
            with PDF.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
    print(f"downloaded {PDF.stat().st_size:,} bytes from {m.group(0)}")


# ---- text layer repair -------------------------------------------------------

def _is_mark(ch: str) -> bool:
    return unicodedata.category(ch) == "Mn"


def _is_pua(ch: str) -> bool:
    return 0xE000 <= ord(ch) <= 0xF8FF


def line_text(line: dict) -> str:
    """One printed line, rebuilt right to left from glyph positions."""
    raw = []
    for s in line["spans"]:
        quran = s["font"].startswith("QCF")
        if s["font"].startswith("KFGQPCArabicSymbols"):
            continue  # honorific signs drawn as symbols (e.g. "r" for رحمه الله): no reliable text
        for c in s["chars"]:
            ch = c["c"]
            if (_is_pua(ch) and not quran) or unicodedata.category(ch) == "Cc":
                continue  # decorative icons and stray control characters
            raw.append({"c": ch, "x0": c["bbox"][0], "x1": c["bbox"][2], "q": quran, "i": len(raw)})
    glyphs = [r for r in raw if not _is_mark(r["c"]) and (r["x1"] - r["x0"] >= 0.05 or r["c"] == " " or r["q"])]
    solid = [g for g in glyphs if g["c"] != " "]
    if not solid:
        return ""
    for g in glyphs:
        g["lig"], g["marks"] = [], []
    for r in raw:
        if r in glyphs:
            continue
        if _is_mark(r["c"]):  # a vowel mark belongs to the glyph it sits on
            host = min(solid, key=lambda g: 0 if g["x0"] - 0.3 <= r["x0"] <= g["x1"] + 0.3
                       else abs((g["x0"] + g["x1"]) / 2 - r["x0"]))
            host["marks"].append(r)
        else:  # a zero-width letter belongs to the ligature glyph that ends where it sits (لا، الله)
            host = min(solid, key=lambda g: abs(g["x1"] - r["x0"]) + (0 if g["i"] > r["i"] else 0.01))
            host["lig"].append(r)
    kept = []
    for g in glyphs:
        if g["c"] == " ":
            mid = (g["x0"] + g["x1"]) / 2
            if any(s["x0"] + 0.2 < mid < s["x1"] - 0.2 for s in solid):
                continue  # a space drawn on top of a letter is not a word break
        kept.append(g)
    kept.sort(key=lambda g: (-g["x1"], g["i"]))
    out: list[str] = []
    for g in kept:
        if g["q"]:
            if not out or out[-1] != VERSE:
                out.append(VERSE)
            continue
        seq = [g["c"]] + [r["c"] for r in sorted(g["lig"], key=lambda r: -r["i"])]
        marks = "".join(m["c"] for m in sorted(g["marks"], key=lambda m: m["i"]))
        # marks go on the lam of لا, and after the whole word-final ligature of الله
        out.append("".join(seq) + marks if len(seq) > 2 else seq[0] + marks + "".join(seq[1:]))
    text = LTR_RUN.sub(lambda m: m.group(0)[::-1], "".join(out))  # numbers read left to right
    text = re.sub(rf"{VERSE}[\s{VERSE}]*", VERSE, text)
    text = re.sub(r"لً(?=[\s.,،؛:!?؟»)]|$)", "لاً", text)  # the لاً ligature loses its alef
    return re.sub(r"\s+", " ", text).strip()


def book_lines() -> list[dict]:
    import fitz  # PyMuPDF: only this script needs it

    doc = fitz.open(PDF)
    lines = []
    for pno, page in enumerate(doc):
        printed = pno  # the book's own page number, read from the running header when present
        page_lines = []
        for b in page.get_text("rawdict")["blocks"]:
            for l in b.get("lines", []):
                text = line_text(l)
                if not text or not l["spans"]:
                    continue
                size = max(s["size"] for s in l["spans"])
                y = l["bbox"][1]
                if size <= 12.5 and y < 45:  # running header with the page number
                    m = re.search(r"\d{1,4}", text)
                    printed = int(m.group(0)) if m else printed
                    continue
                fonts = "/".join(sorted({s["font"] for s in l["spans"]}))
                page_lines.append({"y": y, "x0": l["bbox"][0], "x1": l["bbox"][2],
                                   "size": size, "fonts": fonts, "text": text})
        lines += [{"page": printed, **line} for line in page_lines]
    return lines


# ---- structure ---------------------------------------------------------------

def label_of(line: dict) -> str | None:
    norm = re.sub(r"[:.]", "", normalize_ar(line["text"])).strip()
    if norm in LABELS and ("Manal" in line["fonts"] or "DINNext" in line["fonts"]):
        return LABELS[norm]
    return None


def is_heading(line: dict) -> bool:
    return ("Manal" in line["fonts"] or "AbdoLine" in line["fonts"]) and line["size"] >= 13.5 and not label_of(line)


def parse_toc(lines: list[dict]) -> tuple[dict[int, str], dict[int, str]]:
    """Question titles and their section, from the table of contents (before the first question)."""
    titles: dict[int, str] = {}
    sections: dict[int, str] = {}
    main = sub = ""
    last = None
    for line in lines:
        t = line["text"]
        m = MAIN_SECTION.match(t)
        if m:
            main, sub = f"{m.group(1)}: {m.group(2)}", ""
            continue
        if t.startswith("- ") and "adwaassalaf-Bold" in line["fonts"]:
            sub = t[2:].strip()
            continue
        m = TOC_ITEM.match(t)
        if m:
            last = int(m.group(1))
            titles[last], sections[last] = m.group(2).strip(), " / ".join(x for x in (main, sub) if x)
            continue
        m = re.match(r"^\((\d{1,3})\)\s*[-:]?\s*(.+)$", t)
        if m and "....." not in t:
            last = int(m.group(1))
            titles[last], sections[last] = m.group(2).strip(), " / ".join(x for x in (main, sub) if x)
            continue
        m = TOC_TAIL.match(t)
        if m and last is not None and not t[0].isdigit() and "adwa-assalaf" in line["fonts"]:
            titles[last] += " " + m.group(1).strip()
            last = None
    return titles, sections


def paragraphs(lines: list[dict]) -> list[str]:
    """Join printed lines into paragraphs: a short line or a bullet ends one."""
    if not lines:
        return []
    full = max(l["x1"] - l["x0"] for l in lines)
    paras: list[str] = []
    cur = ""
    prefix = ""
    for k, line in enumerate(lines):
        t = line["text"]
        if t in ("3", "o", "•"):
            prefix = "• "
            continue
        m = re.fullmatch(r"[()\-]?(\d{1,2})[()\-]?", t)
        if m:
            prefix = f"({m.group(1)}) "
            continue
        if t.startswith("3") and not t[1:2].isdigit():
            t, prefix = t[1:].strip(), "• "
        if prefix:
            if cur:
                paras.append(cur)
            cur, prefix = prefix + t, ""
        else:
            cur = f"{cur} {t}".strip()
        if line["x1"] - line["x0"] < 0.8 * full:
            paras.append(cur)
            cur = ""
    if cur:
        paras.append(cur)
    return paras


# ---- verses ------------------------------------------------------------------

def _sura_numbers() -> dict[str, int]:
    names = {}
    for p in get_corpus().passages.values():
        if p.kind == "quran":
            n = normalize_ar(p.data["sura_name_ar"])
            names[n] = names[n.removeprefix("ال")] = p.data["sura"]
    return names


def place_verses(text: str, refs: list[str], report: list, qid: str) -> str:
    """Each ﴿verse﴾ followed by its reference becomes Mushaf markers; others become ﴿…﴾."""
    suras = _sura_numbers()
    corpus = get_corpus()
    # a verse that wraps over lines (or a run of verses under one reference) is one placeholder
    text = re.sub(rf"﴿?[\s.…]*{VERSE}(?:[\s﴿﴾.…]*{VERSE})*[\s.…]*﴾?", f"﴿{VERSE}﴾", text)
    out, pos = [], 0
    for m in re.finditer(rf"﴿{VERSE}﴾", text):
        out.append(text[pos:m.start()])
        pos = m.end()
        ref = REF.match(text[pos:])
        ids = []
        if ref:
            name = normalize_ar(ref.group(1)).strip()
            sura = suras.get(name) or suras.get(name.removeprefix("ال"))
            a = int(ref.group(2).translate(DIGITS))
            b = int((ref.group(3) or ref.group(2)).translate(DIGITS))
            a, b = min(a, b), max(a, b)  # a range drawn right to left can come out reversed (54-53)
            if sura and a <= b <= a + 10:
                ids = [f"q:{sura}:{x}" for x in range(a, b + 1) if corpus.get(f"q:{sura}:{x}")]
        if ids:
            pos += ref.end()
            refs += [i for i in ids if i not in refs]
            out.append("\n" + "\n".join(f"[[{i}]]" for i in ids) + "\n")
        else:
            report.append({"id": qid, "after": text[pos:pos + 40]})
            out.append("﴿…﴾")
    out.append(text[pos:])
    clean = re.sub(r"[ \t]+\n", "\n", "".join(out))
    return re.sub(r"\n{3,}", "\n\n", clean).strip()


# ---- build -------------------------------------------------------------------

def build() -> None:
    download()
    lines = book_lines()
    starts = [i for i, l in enumerate(lines) if label_of(l) == "question"]
    titles, sections = parse_toc(lines[:starts[0]])
    rows, report = [], []
    for k, s in enumerate(starts):
        head = s
        while head > 0 and is_heading(lines[head - 1]):
            head -= 1
        nums = [int(m.group(1)) for l in lines[head:s] for m in HEADING_NUM.finditer(l["text"])]
        n = nums[0] if nums else (rows[-1]["n"] + 1 if rows else 1)
        end = len(lines)
        if k + 1 < len(starts):
            end = starts[k + 1]
            while end > s and is_heading(lines[end - 1]):
                end -= 1
        parts: dict[str, list[dict]] = {"question": []}
        current = "question"
        for line in lines[s + 1:end]:
            lab = label_of(line)
            if lab:
                current = lab
                parts.setdefault(current, [])
                continue
            parts.setdefault(current, []).append(line)
        qid = f"b:{n}"
        refs: list[str] = []
        text = {key: "\n".join(paragraphs(v)) for key, v in parts.items()}
        rows.append({
            "id": qid, "n": n,
            "title": titles.get(n) or " ".join(l["text"] for l in lines[head:s])[:200],
            "section": sections.get(n, ""),
            "question": place_verses(text.get("question", ""), refs, report, qid),
            "similar": [re.sub(r"^•\s*", "", p) for p in paragraphs(parts.get("similar", []))],
            "gist": place_verses(text.get("gist", ""), refs, report, qid),
            "short_answer": place_verses(text.get("short", ""), refs, report, qid),
            "answer": place_verses(text.get("detailed", "") or text.get("answer", ""), refs, report, qid),
            "refs": refs, "page": lines[s]["page"], "url_ar": PACKAGE_URL,
        })
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    nums = [r["n"] for r in rows]
    missing = sorted(set(range(1, max(nums) + 1)) - set(nums))
    print(f"wrote {len(rows)} questions to {OUT.relative_to(ROOT)} (numbers 1-{max(nums)}, missing {missing[:20]}); "
          f"{sum(len(r['refs']) for r in rows)} verse markers, {len(report)} verses without a reference "
          f"(see {REPORT.relative_to(ROOT)})")


if __name__ == "__main__":
    build()
