"""Videos API: IslamHouse videos in every language IslamHouse offers. Owner: Mushari.

GET  /api/videos?lang=<IslamHouse language code>&page=1&per_page=12&topic=<topic id>
POST /api/videos/search {lang, q, topic?, page?, per_page?}   same result, filtered by the search words
  -> {state, items, page, pages, total, topics, source}
Search words go in a POST body, like /api/ask, so they never land in access logs. Nothing about searches
or viewing is stored.
state is "loading" while the first index is built (the client polls), "ready" or "unavailable".
GET /api/videos/languages -> [{code, name, count}]: every language with videos (107 of 133 on IslamHouse),
so seekers who read neither Arabic nor English can watch in their own language.
POST /api/videos/related {lang, q, hints?, k?} -> {state, items, source}: up to k videos related to a
question from the Ask page (related.py). Suggestions only: answers never cite videos.
"""
from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..rag.public import semantic_encoder, semantic_status
from . import islamhouse, related

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


class RelatedIn(BaseModel):
    lang: str = "ar"
    q: str = Field("", max_length=2000)
    hints: list[Annotated[str, Field(max_length=200)]] = Field(default_factory=list, max_length=12)
    k: int = Field(3, ge=1, le=6)


@router.post("/videos/related")
def related_videos(body: RelatedIn):
    """Videos to suggest under an answer. A POST body, like /api/ask, so the question never reaches access logs;
    nothing is stored."""
    lang = body.lang if islamhouse.is_language(body.lang) else "ar"
    requested = related.wants_video(body.q)        # the person asked for a video: the page says so if none fits
    idx, state = islamhouse.get_index(lang)
    if idx is None or not body.q.strip():
        return {"state": state if idx is None else "ready", "items": [], "requested": requested, "source": SOURCE}
    enc = semantic_encoder()
    # E5 still loading (first seconds after start-up), or this language's videos being embedded: ask again
    # shortly instead of answering with the stricter words-only match.
    if (enc is None and semantic_status() == "loading") or related.pending(idx, enc):
        return {"state": "loading", "items": [], "requested": requested, "source": SOURCE}
    items = related.related(idx, body.q, body.hints, body.k, encoder=enc)
    return {"state": "ready", "items": items, "requested": requested, "source": SOURCE}


def warm() -> None:
    """Called from the app's startup thread (main.py)."""
    islamhouse.warm()
    if os.getenv("SABEELI_OFFLINE", "").strip().lower() not in {"1", "true", "yes", "on"}:
        related.prepare(islamhouse.get_index, semantic_encoder)   # embed ar/en videos once both are ready
