"""IslamHouse API v3 client for the videos section. Owner: Mushari.

IslamHouse (islamhouse.com) is listed in the challenge's scholarly package, p. 9, as one of the
association's platforms ("... وصوتيات ومرئيات مصنّفة موضوعياً"), with this API as its developer
interface. The key below is the public key published in the official Postman documentation
(documenter.getpostman.com/view/7929737/TzkyMfPc).

We never re-host media: the app plays MP4 files straight from IslamHouse's CDN or their YouTube
embeds, and every item links back to its IslamHouse page.

Why a local index: the API's topic filter is not recursive (a video filed under
"Fiqh > Prayer > How to Pray" is not returned for "Fiqh"), so we read the whole video list of a
language once (about 20-35 calls) plus each category's direct videos (about 440 calls,
in parallel), then filter and page locally. Everything stays in memory for CACHE_TTL.
"""
from __future__ import annotations

import html
import logging
import os
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import httpx

from ...core.textnorm import normalize_ar

log = logging.getLogger("sabeeli.videos")

# Public key from IslamHouse's own API documentation; override with SABEELI_ISLAMHOUSE_KEY if they issue a new one.
KEY = os.getenv("SABEELI_ISLAMHOUSE_KEY") or "paV29H2gm56kvLPy"
BASE = f"https://api3.islamhouse.com/v3/{KEY}"
HEADERS = {"User-Agent": "Sabeeli/0.1 (+https://github.com/mushari44/Islam-hackthon)"}   # the API refuses requests without one
PLAYABLE = {"MP4", "YOUTUBE"}
LANGS = ("ar", "en")
CACHE_TTL = 6 * 3600
RETRY_AFTER = 60          # seconds to wait before trying IslamHouse again after a failure
PAGE = 50


def _get(client: httpx.Client, path: str):
    for attempt in range(3):
        try:
            r = client.get(f"{BASE}/{path}", headers=HEADERS, timeout=30)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError):
            if attempt == 2:
                raise
            time.sleep(0.6 * (attempt + 1))
    return None


def _strip(text: str | None) -> str:
    """IslamHouse descriptions may carry HTML and hashtags; show plain text only."""
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>|</p>", "\n", text, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()


def _norm(text: str | None) -> str:
    """Search form: Arabic letters unified (hamza, taa marbuta, diacritics); other scripts case- and accent-folded."""
    folded = unicodedata.normalize("NFKD", normalize_ar(text or "").casefold())
    return "".join(c for c in folded if not unicodedata.combining(c))     # "priere" finds "prière"


def _attachment(a: dict) -> dict | None:
    kind = (a.get("extension_type") or "").upper()
    url = a.get("url") or ""
    if kind not in PLAYABLE or not url.startswith("https://"):
        return None
    if kind == "YOUTUBE":
        # privacy-enhanced mode: no YouTube cookies until the viewer presses play
        url = url.replace("https://www.youtube.com/", "https://www.youtube-nocookie.com/")
    return {"kind": "mp4" if kind == "MP4" else "youtube", "url": url,
            "label": _strip(a.get("description")), "size": a.get("size") if kind == "MP4" else None}


def _item(raw: dict, lang: str) -> dict | None:
    parts = [p for p in (_attachment(a) for a in raw.get("attachments") or []) if p]
    if not parts:            # some "videos" are really PDFs; drop them
        return None
    if any(p["kind"] == "mp4" for p in parts):
        # many items list the same talk twice (YouTube embed + MP4 file): prefer the file on IslamHouse
        parts = [p for p in parts if p["kind"] == "mp4"]
    authors = [p.get("title") for p in raw.get("prepared_by") or [] if p.get("title")]
    return {
        "id": raw["id"],
        "title": _strip(raw.get("title")),
        "description": _strip(raw.get("full_description") or raw.get("description")),
        "thumbnail": raw.get("image") or None,
        "authors": authors,
        "lang": lang,
        "added": raw.get("add_date"),
        "parts": parts,
        "page_url": f"https://islamhouse.com/{lang}/videos/{raw['id']}/",
        "topic": None,
        "topic_id": None,
    }


class Index:
    """All playable videos of one language, with their top-level topics."""

    def __init__(self, lang: str):
        self.lang = lang
        self.items: list[dict] = []
        self.topics: list[dict] = []
        self.built_at = 0.0

    def build(self) -> None:
        started = time.time()
        with httpx.Client() as client:
            first = _get(client, f"main/videos/{self.lang}/{self.lang}/1/{PAGE}/json")
            pages = int(first.get("links", {}).get("pages_number") or 1)
            raws = [x for x in first.get("data") or [] if isinstance(x, dict)]
            with ThreadPoolExecutor(8) as ex:
                for chunk in ex.map(lambda p: _get(client, f"main/videos/{self.lang}/{self.lang}/{p}/{PAGE}/json"),
                                    range(2, pages + 1)):
                    data = chunk.get("data") if isinstance(chunk, dict) else None
                    raws.extend(x for x in data or [] if isinstance(x, dict))
            by_id: dict[int, dict] = {}
            for raw in raws:
                it = _item(raw, self.lang)
                if it:
                    by_id.setdefault(it["id"], it)

            # topic tree -> for every category, the top-level topic it belongs to
            tree = _get(client, f"main/get-object-category-tree/{self.lang}/json")
            owner: dict[int, tuple[dict, str]] = {}     # category id -> (top-level topic, leaf title)

            def walk(cat: dict, top: dict) -> None:
                owner[cat["id"]] = (top, cat.get("title") or "")
                for sub in cat.get("sub_categories") or []:
                    walk(sub, top)

            tops = tree.get("sub_categories") or []
            if any(not t.get("title") for t in tops) and self.lang != "en":
                # some languages have no translated topic names: fall back to the English ones
                names = {t["id"]: t.get("title") for t in (_get(client, "main/get-object-category-tree/en/json") or {}).get("sub_categories") or []}
                for t in tops:
                    t["title"] = t.get("title") or names.get(t["id"]) or ""
            for top in tops:
                walk(top, top)

            def direct_videos(cat_id: int) -> tuple[int, list[int]]:
                ids: list[int] = []
                page, pages_n = 1, 1
                try:
                    while page <= pages_n:
                        r = _get(client, f"main/get-category-items/{cat_id}/videos/{self.lang}/{self.lang}/{page}/{PAGE}/json")
                        data = r.get("data") if isinstance(r, dict) else None
                        if not isinstance(data, list):     # empty categories answer with a message string
                            break
                        pages_n = int(r.get("links", {}).get("pages_number") or 0)
                        ids.extend(x["id"] for x in data if isinstance(x, dict) and "id" in x)
                        page += 1
                except httpx.HTTPError:
                    log.info("videos %s: category %s skipped", self.lang, cat_id)
                return cat_id, ids

            members: dict[int, set[int]] = {t["id"]: set() for t in tops}
            with ThreadPoolExecutor(8) as ex:
                for cat_id, ids in ex.map(direct_videos, list(owner)):
                    top, leaf = owner[cat_id]
                    for vid in ids:
                        if vid in by_id:
                            members[top["id"]].add(vid)
                            it = by_id[vid]
                            if it["topic_id"] is None:   # first topic wins; a video can sit under several
                                it["topic_id"], it["topic"] = top["id"], leaf or top.get("title")

        self.items = sorted(by_id.values(), key=lambda x: x.get("added") or 0, reverse=True)
        self.members = members
        self.topics = sorted(
            ({"id": t["id"], "title": t.get("title") or "", "count": len(members[t["id"]])} for t in tops
             if members[t["id"]]),
            key=lambda t: -t["count"])
        self.built_at = time.time()
        log.info("videos %s: %d playable items, %d topics (%.0fs)", self.lang, len(self.items), len(self.topics),
                 self.built_at - started)

    def search(self, items: list[dict], q: str) -> list[dict]:
        """Every query word must appear in the title, description, authors or topic; title hits rank first.
        The IslamHouse v3 API has no search endpoint, so we search the cached list."""
        # drop the Arabic article so "الصلاة" also finds "صفة صلاة"
        terms = [t[2:] if t.startswith("ال") and len(t) > 4 else t for t in _norm(q).split() if t]
        if not terms:
            return items
        scored = []
        for it in items:
            title = _norm(it["title"])
            rest = _norm(" ".join([it["description"], " ".join(it["authors"]), it.get("topic") or ""]))
            if all(t in title or t in rest for t in terms):
                score = sum(3 for t in terms if t in title) + sum(1 for t in terms if t in rest)
                scored.append((score, it.get("added") or 0, it))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [it for _, _, it in scored]

    def query(self, topic: int | None, page: int, per_page: int, q: str = "") -> dict:
        items = self.items if not topic else [x for x in self.items if x["id"] in self.members.get(topic, set())]
        items = self.search(items, q)
        pages = max(1, -(-len(items) // per_page))
        page = min(max(1, page), pages)
        start = (page - 1) * per_page
        return {"items": items[start:start + per_page], "page": page, "pages": pages, "total": len(items)}


_languages: dict = {"at": 0.0, "list": []}


def languages() -> list[dict]:
    """Languages that have at least one video on IslamHouse: [{code, name, count}], largest first."""
    if _languages["list"] and time.time() - _languages["at"] < CACHE_TTL:
        return _languages["list"]
    with httpx.Client() as client:
        home = _get(client, "main/home/json")
        langs = [(x["language_code"], x.get("title") or x["language_code"]) for x in home.get("data") or []]

        def count(code: str) -> int:
            try:
                blocks = _get(client, f"main/sitecontent/{code}/{code}/json")
            except httpx.HTTPError:
                return 0
            return next((b.get("items_count") or 0 for b in blocks or [] if isinstance(b, dict) and b.get("block_name") == "videos"), 0)

        with ThreadPoolExecutor(8) as ex:
            counts = list(ex.map(count, [c for c, _ in langs]))
    result = sorted(({"code": c, "name": n, "count": k} for (c, n), k in zip(langs, counts) if k), key=lambda x: -x["count"])
    _languages.update(at=time.time(), list=result)
    return result


def is_language(code: str) -> bool:
    return code in LANGS or any(x["code"] == code for x in _languages["list"]) or bool(re.fullmatch(r"[a-z]{2,3}", code))


_indexes: dict[str, Index] = {}
_building: dict[str, threading.Thread] = {}
_errors: dict[str, float] = {}      # language -> time of the last failed build
_lock = threading.Lock()


def _build(lang: str) -> None:
    try:
        idx = Index(lang)
        idx.build()
        _indexes[lang] = idx
        _errors.pop(lang, None)
    except Exception as exc:  # noqa: BLE001 - reported to the client as "unavailable"
        log.warning("videos %s: IslamHouse unavailable: %s", lang, exc)
        _errors[lang] = time.time()
    finally:
        _building.pop(lang, None)


def get_index(lang: str) -> tuple[Index | None, str]:
    """Returns (index, state); state is ready, loading or unavailable. Builds in the background."""
    idx = _indexes.get(lang)
    fresh = idx is not None and time.time() - idx.built_at < CACHE_TTL
    failed_recently = time.time() - _errors.get(lang, 0) < RETRY_AFTER
    with _lock:
        if not fresh and lang not in _building and not failed_recently:
            t = threading.Thread(target=_build, args=(lang,), daemon=True)
            _building[lang] = t
            t.start()
    if idx is not None:
        return idx, "ready"            # a stale index keeps serving while it is rebuilt
    return None, "unavailable" if failed_recently else "loading"


def warm(langs: tuple[str, ...] = LANGS) -> None:
    """Start building the Arabic and English indexes at startup, so the first visitor doesn't wait.
    Skipped in tests and offline demos (SABEELI_OFFLINE=1)."""
    if os.getenv("SABEELI_OFFLINE", "").strip().lower() in {"1", "true", "yes", "on"}:
        return
    for lang in langs:
        get_index(lang)
