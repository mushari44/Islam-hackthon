"""Build data/corpus/hadith.jsonl from HadeethEnc (hadeethenc.com).

HadeethEnc is the Encyclopedia of Translated Prophetic Hadiths run by the
Islamic Content Service Association, which the challenge's scholarly package
lists as an approved source. Every record keeps the grade and attribution the
encyclopedia gives, so the app never states a hadith without its source and
grade.

Raw API responses are cached in data/raw/hadith/ (git-ignored) so the script
can be re-run without hitting the API again.

Usage:  python scripts/ingest_hadith.py [--workers 6]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "hadith"
OUT = ROOT / "data" / "corpus" / "hadith.jsonl"
CATS = ROOT / "data" / "corpus" / "hadith_categories.json"

API = "https://hadeethenc.com/api/v1"
LANGS = ("ar", "en")


def get_json(client: httpx.Client, url: str, tries: int = 5):
    for attempt in range(tries):
        try:
            r = client.get(url, timeout=40)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as exc:
            if attempt == tries - 1:
                print(f"  ! giving up on {url}: {exc}", file=sys.stderr)
                return None
            time.sleep(1.5 * (attempt + 1))


def list_ids(client: httpx.Client, category_id: str) -> set[str]:
    ids: set[str] = set()
    page = 1
    while True:
        data = get_json(client, f"{API}/hadeeths/list/?language=ar&category_id={category_id}&page={page}&per_page=100")
        if not data or not data.get("data"):
            break
        ids.update(str(h["id"]) for h in data["data"])
        meta = data.get("meta") or {}
        if int(meta.get("current_page", page)) >= int(meta.get("last_page", page)):
            break
        page += 1
    return ids


def fetch_one(client: httpx.Client, hid: str, lang: str):
    path = RAW / lang / f"{hid}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    data = get_json(client, f"{API}/hadeeths/one/?language={lang}&id={hid}")
    if data:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "Sabeeli-ingest/0.1 (hackathon; contact via repo)"}
    with httpx.Client(headers=headers, follow_redirects=True) as client:
        cats = {lang: get_json(client, f"{API}/categories/list/?language={lang}") or [] for lang in LANGS}
        CATS.write_text(json.dumps({
            str(c["id"]): {
                "ar": c["title"],
                "en": next((e["title"] for e in cats["en"] if e["id"] == c["id"]), ""),
                "parent": c.get("parent_id"),
            } for c in cats["ar"]
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(cats['ar'])} categories")

        all_ids: set[str] = set()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for ids in pool.map(lambda c: list_ids(client, str(c["id"])), cats["ar"]):
                all_ids |= ids
        ordered = sorted(all_ids, key=int)
        print(f"{len(ordered)} unique hadith ids")

        records = {}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for lang in LANGS:
                results = pool.map(lambda h: (h, fetch_one(client, h, lang)), ordered)
                for i, (hid, data) in enumerate(results, 1):
                    if data:
                        records.setdefault(hid, {})[lang] = data
                    if i % 500 == 0:
                        print(f"  {lang}: {i}/{len(ordered)}")

    count = 0
    with OUT.open("w", encoding="utf-8") as f:
        for hid in ordered:
            rec = records.get(hid, {})
            ar, en = rec.get("ar"), rec.get("en")
            if not ar:
                continue
            row = {
                "id": f"h:{hid}",
                "kind": "hadith",
                "hid": int(hid),
                "title_ar": ar.get("title", "").strip(),
                "title_en": (en or {}).get("title", "").strip(),
                "text_ar": ar.get("hadeeth", "").strip(),
                "text_en": (en or {}).get("hadeeth", "").strip(),
                "attribution_ar": ar.get("attribution", "").strip(),
                "attribution_en": (en or {}).get("attribution", "").strip(),
                "grade_ar": ar.get("grade", "").strip(),
                "grade_en": (en or {}).get("grade", "").strip(),
                "explanation_ar": ar.get("explanation", "").strip(),
                "explanation_en": (en or {}).get("explanation", "").strip(),
                "hints_ar": as_list(ar.get("hints")),
                "hints_en": as_list((en or {}).get("hints")),
                "reference_ar": (ar.get("reference") or "").strip(),
                "categories": [str(c) for c in (ar.get("categories") or [])],
                "url_ar": f"https://hadeethenc.com/ar/browse/hadith/{hid}",
                # the English page only exists when the hadith has an English translation
                "url_en": f"https://hadeethenc.com/en/browse/hadith/{hid}" if (en or {}).get("hadeeth")
                else f"https://hadeethenc.com/ar/browse/hadith/{hid}",
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    print(f"wrote {count} hadiths to {OUT}")
    return 0 if count else 1


if __name__ == "__main__":
    sys.exit(main())
