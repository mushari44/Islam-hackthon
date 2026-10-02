"""Build data/corpus/quran.jsonl from the approved package's public APIs.

Sources (all listed in the challenge's scholarly package):
  - QuranEnc (quranenc.com, Islamic Content Service Association):
      * arabic_moyassar -> Uthmani verse text (King Fahd Complex) + At-Tafsir Al-Muyassar
      * english_rwwad   -> English translation of the meanings (Rowwad Translation Center)
  - mp3quran.net public API -> surah names (Arabic / English)

The verse text is stored exactly as the reference returns it. The app shows it
verbatim and never lets the model generate it.

Usage:  python scripts/ingest_quran.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "corpus" / "quran.jsonl"
META = ROOT / "data" / "corpus" / "quran_meta.json"

QURANENC = "https://quranenc.com/api/v1/translation/sura/{key}/{sura}"
SUWAR = "https://www.mp3quran.net/api/v3/suwar?language={lang}"
AR_KEY = "arabic_moyassar"
EN_KEY = "english_rwwad"

FOOTNOTE_MARK = re.compile(r"\[\d+\]")


def get_json(client: httpx.Client, url: str, tries: int = 4):
    for attempt in range(tries):
        try:
            r = client.get(url, timeout=40)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as exc:
            if attempt == tries - 1:
                raise RuntimeError(f"failed: {url}: {exc}") from exc
            time.sleep(2 ** attempt)


def fetch_sura(client: httpx.Client, sura: int):
    ar = get_json(client, QURANENC.format(key=AR_KEY, sura=sura))["result"]
    en = get_json(client, QURANENC.format(key=EN_KEY, sura=sura))["result"]
    by_aya = {int(x["aya"]): x for x in en}
    rows = []
    for item in ar:
        aya = int(item["aya"])
        e = by_aya.get(aya, {})
        rows.append({
            "sura": sura,
            "aya": aya,
            "text_ar": item["arabic_text"],
            "tafsir_ar": (item.get("translation") or "").strip(),
            "translation_en": FOOTNOTE_MARK.sub("", e.get("translation") or "").strip(),
            "footnotes_en": (e.get("footnotes") or "").strip(),
        })
    return rows


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "Sabeeli-ingest/0.1 (hackathon; contact via repo)"}
    with httpx.Client(headers=headers, follow_redirects=True) as client:
        names_ar = {s["id"]: s["name"].strip() for s in get_json(client, SUWAR.format(lang="ar"))["suwar"]}
        names_en = {s["id"]: s["name"].strip() for s in get_json(client, SUWAR.format(lang="eng"))["suwar"]}
        with ThreadPoolExecutor(max_workers=4) as pool:
            suras = list(pool.map(lambda s: fetch_sura(client, s), range(1, 115)))

    count = 0
    with OUT.open("w", encoding="utf-8") as f:
        for sura_rows in suras:
            for row in sura_rows:
                s, a = row["sura"], row["aya"]
                row = {
                    "id": f"q:{s}:{a}",
                    "kind": "quran",
                    "sura_name_ar": names_ar.get(s, ""),
                    "sura_name_en": names_en.get(s, ""),
                    **row,
                    "url_ar": f"https://quranenc.com/ar/browse/{AR_KEY}/{s}#{a}",
                    "url_en": f"https://quranenc.com/en/browse/{EN_KEY}/{s}#{a}",
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                count += 1

    META.write_text(json.dumps({
        "verses": count,
        "sources": {
            "text_ar": "Uthmani text via QuranEnc (King Fahd Complex edition)",
            "tafsir_ar": f"QuranEnc {AR_KEY} (At-Tafsir Al-Muyassar)",
            "translation_en": f"QuranEnc {EN_KEY} (Rowwad Translation Center)",
            "sura_names": "mp3quran.net API v3",
        },
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {count} verses to {OUT}")
    return 0 if count == 6236 else 1


if __name__ == "__main__":
    sys.exit(main())
