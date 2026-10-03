"""Videos API: IslamHouse videos in every language IslamHouse offers. Owner: Mushari.

GET  /api/videos?lang=<IslamHouse language code>&page=1&per_page=12&topic=<topic id>
POST /api/videos/search {lang, q, topic?, page?, per_page?}   same result, filtered by the search words
  -> {state, items, page, pages, total, topics, source}
Search words go in a POST body, like /api/ask, so they never land in access logs. Nothing about searches
or viewing is stored.
state is "loading" while the first index is built (the client polls), "ready" or "unavailable".
GET /api/videos/languages -> [{code, name, count}]: every language with videos (107 of 133 on IslamHouse),
so seekers who read neither Arabic nor English can watch in their own language.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from . import islamhouse

router = APIRouter(prefix="/api")

SOURCE = {"name": "IslamHouse", "url": "https://islamhouse.com/"}


@router.get("/videos/languages")
def video_languages():
    try:
        return islamhouse.languages()
    except Exception:  # noqa: BLE001
        raise HTTPException(503, "unavailable") from None


class SearchIn(BaseModel):
    lang: str = "ar"
    q: str = Field("", max_length=100)
    topic: int | None = None
    page: int = Field(1, ge=1)
    per_page: int = Field(12, ge=1, le=48)


def _result(lang: str, topic: int | None, page: int, per_page: int, q: str = "") -> dict:
    lang = lang if islamhouse.is_language(lang) else "ar"
    idx, state = islamhouse.get_index(lang)
    if idx is None:
        return {"state": state, "items": [], "page": 1, "pages": 1, "total": 0, "topics": [], "source": SOURCE}
    return {"state": "ready", **idx.query(topic, page, per_page, q.strip()), "topics": idx.topics, "source": SOURCE}


@router.get("/videos")
def list_videos(lang: str = Query("ar"), page: int = Query(1, ge=1), per_page: int = Query(12, ge=1, le=48),
                topic: int | None = None):
    return _result(lang, topic, page, per_page)


@router.post("/videos/search")
def search_videos(body: SearchIn):
    return _result(body.lang, body.topic, body.page, body.per_page, body.q)


def warm() -> None:
    """Called from the app's startup thread (main.py)."""
    islamhouse.warm()
