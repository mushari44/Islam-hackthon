"""RAG API: ask (text and/or photo), feedback, source lookup. Owner: Mushari.

Contract used by frontend/src/features/rag (see docs/API.md):
  POST /api/ask            multipart: question, lang, image? -> Answer
  POST /api/ask/{id}/feedback {helpful, reason}
  GET  /api/sources/{id}?lang=ar|en -> source card
  GET  /api/corpus         -> counts and source list
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...core.db import get_db
from ..auth.public import SeekerSession, seeker
from .corpus import get_corpus
from .models import ChatTurn, purge_expired, recent_turns
from .pipeline import AskContext, ask, plain_text

router = APIRouter(prefix="/api")

MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _history(db: Session, sid: str) -> list[dict]:
    out = []
    for turn in recent_turns(db, sid, limit=4):
        out.append({"role": "user", "text": turn.question})
        out.append({"role": "assistant", "text": plain_text(turn.answer)})
    return out


@router.post("/ask")
def ask_question(question: str = Form(""), lang: str = Form("ar"), image: UploadFile | None = File(None),
                 me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    purge_expired(db)
    data, media_type = None, ""
    if image is not None and image.filename:
        media_type = (image.content_type or "").lower()
        if media_type not in IMAGE_TYPES:
            raise HTTPException(415, "unsupported image type")
        data = image.file.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "image too large (max 5 MB)")
    if not question.strip() and not data:
        raise HTTPException(400, "empty question")
    result = ask(AskContext(question=question, ui_lang="ar" if lang == "ar" else "en",
                            history=_history(db, me.id), image=data, image_type=media_type))
    turn = ChatTurn(session_id=me.id, question=question.strip()[:2000] or "(image)", lang=result["lang"],
                    level=result.get("level", "A"), kind=result["kind"], mode=result["mode"],
                    answer={k: result.get(k) for k in ("segments", "sources", "kind", "level", "lang", "quote_check")})
    db.add(turn)
    db.commit()
    return {"turn_id": turn.id, **result}


class Feedback(BaseModel):
    helpful: bool
    reason: str = Field(default="", max_length=64)


@router.post("/ask/{turn_id}/feedback")
def feedback(turn_id: int, body: Feedback, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    turn = db.get(ChatTurn, turn_id)
    if not turn or turn.session_id != me.id:
        raise HTTPException(404, "not found")
    turn.helpful, turn.feedback_reason = body.helpful, body.reason
    db.commit()
    return {"ok": True}


@router.get("/sources/{pid}")
def source_card(pid: str, lang: str = "ar"):
    p = get_corpus().get(pid)
    if not p:
        raise HTTPException(404, "not found")
    return p.card("ar" if lang == "ar" else "en")


@router.get("/corpus")
def corpus_info():
    return get_corpus().stats()
