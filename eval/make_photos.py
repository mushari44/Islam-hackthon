"""Make the 10 synthetic photos the evaluation uses (eval/photos/). Owner: Mushari.

Each photo is printed text only (no people, no chats): a verse as a poster or a page would show it, some
with a deliberate mistake, one hadith, one saying that is not a verse, and two hard to read (blurred,
small and tilted). Verse text comes from the corpus (data/corpus/quran.jsonl) in plain script; the
mistakes are written here on purpose and listed in eval/cases.csv.

Usage: python eval/make_photos.py   (needs Chrome or Edge for rendering Arabic, and Pillow)
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "photos"
BROWSERS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            "google-chrome", "chromium", "chromium-browser", "microsoft-edge"]
# Uthmani marks and small letters dropped, ٱ written ا: the plain script of most printed posters.
MARKS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")


def verse(ref: str) -> str:
    sura, aya = ref.split(":")
    for line in open(ROOT / "data" / "corpus" / "quran.jsonl", encoding="utf-8"):
        d = json.loads(line)
        if d["sura"] == int(sura) and d["aya"] == int(aya):
            return MARKS.sub("", d["text_ar"]).replace("ٱ", "ا").strip()
    raise KeyError(ref)


def verses(*refs: str) -> str:
    return " ".join(f"{verse(r)} ({r.split(':')[1]})" for r in refs)


def photos() -> dict[str, dict]:
    kursi = verse("2:255")
    hujurat = verse("49:13")
    return {
        "p01_ikhlas.png": {"text": verses("112:1", "112:2", "112:3", "112:4"), "title": "سورة الإخلاص"},
        # deliberate mistake: «نوم» -> «نعاس»
        "p02_kursi_mistake.png": {"text": kursi[: kursi.index("له ما")].replace("نوم", "نعاس").strip()},
        "p03_fatiha_blurred.png": {"text": verses("1:1", "1:2", "1:3", "1:4"), "title": "سورة الفاتحة",
                                   "degrade": "blur"},
        "p04_hadith_niyyat.png": {"text": "قال رسول الله ﷺ: «إنما الأعمال بالنيات، وإنما لكل امرئ ما نوى»",
                                  "title": "حديث شريف", "quote": False},
        # a saying, not a verse, printed as if it were one
        "p05_saying_as_verse.png": {"text": "﴿النظافة من الإيمان والوسخ من الشيطان﴾", "title": "آية"},
        "p06_no_compulsion.png": {"text": verse("2:256")[: verse("2:256").index("فمن")].strip()},
        # deliberate mistake: «لتعارفوا» -> «لتتعاونوا»
        "p07_hujurat_mistake.png": {"text": hujurat[: hujurat.index("إن الله")].replace("لتعارفوا", "لتتعاونوا").strip()},
        "p08_yusr.png": {"text": verses("94:5", "94:6"), "title": "سورة الشرح"},
        "p09_fatiha_small_tilted.png": {"text": verses("1:2", "1:3", "1:4"), "degrade": "small"},
        "p10_rahma.png": {"text": verse("21:107")},
    }


def html(item: dict) -> str:
    text = item["text"] if item.get("quote") is False or item["text"].startswith("﴿") else f"﴿{item['text']}﴾"
    title = f"<h2>{item['title']}</h2>" if item.get("title") else ""
    return f"""<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><style>
body {{ margin: 0; background: #f4efe2; font-family: 'Traditional Arabic', 'Amiri', 'Noto Naskh Arabic', serif; }}
.page {{ margin: 28px; padding: 28px 36px; border: 3px double #8a6d3b; background: #fbf8ef; color: #2b2116; }}
h2 {{ margin: 0 0 14px; text-align: center; font-size: 30px; color: #6b4f1d; }}
p {{ margin: 0; font-size: 38px; line-height: 1.9; text-align: center; }}
</style></head><body><div class="page">{title}<p>{text}</p></div></body></html>"""


def render(page: str, out: Path) -> None:
    browser = next((b for b in BROWSERS if Path(b).exists() or shutil.which(b)), None)
    if not browser:
        sys.exit("Chrome or Edge is needed to render Arabic text")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "page.html"
        src.write_text(page, encoding="utf-8")
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--screenshot={out}",
                        "--window-size=1000,560", src.as_uri()], check=True, capture_output=True, timeout=60)


def trim(path: Path) -> None:
    """Cut the empty page below the printed text (the window is taller than most texts)."""
    img = Image.open(path).convert("RGB")
    box = ImageChops.difference(img, Image.new("RGB", img.size, img.getpixel((2, img.height - 2)))).getbbox()
    if box:
        img.crop((0, 0, img.width, min(img.height, box[3] + 28))).save(path)


def degrade(path: Path, how: str) -> None:
    img = Image.open(path).convert("RGB")
    if how == "blur":       # out of focus
        img = img.filter(ImageFilter.GaussianBlur(3.2))
    elif how == "small":    # taken from afar, a little tilted
        img = img.resize((img.width // 3, img.height // 3)).rotate(7, expand=True, fillcolor=(90, 90, 90))
    img.save(path)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, item in photos().items():
        out = OUT / name
        render(html(item), out)
        trim(out)
        if item.get("degrade"):
            degrade(out, item["degrade"])
        print(name, out.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
