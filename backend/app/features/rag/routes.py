"""RAG API: ask (text and/or photo), feedback, source lookup. Owner: Mushari.

Contract used by frontend/src/features/rag (see docs/API.md):
  POST /api/ask            multipart: question, lang, image?, conversation_id? -> Answer
  GET  /api/conversations  -> this seeker's chats, newest first
  GET  /api/conversations/{id} -> one chat's turns;  DELETE it
  POST /api/ask/{id}/feedback {helpful, reason}
  GET  /api/sources/{id}?lang=ar|en -> source card
  GET  /api/corpus         -> counts and source list
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ...core.db import get_db, iso, utcnow
from ..auth.public import SeekerSession, account_session_ids, seeker
from .corpus import get_corpus
from .models import ChatTurn, Conversation, adopt_loose_turns, purge_expired, recent_turns, title_for
from .pipeline import AskContext, ask, plain_text

router = APIRouter(prefix="/api")

MAX_IMAGE_BYTES = 5 * 1024 * 1024
# What a saved turn keeps to show the answer again. Cards are rebuilt from `sources`; the trace (which can
# hold text the pipeline removed) and timings are never stored.
SAVED_KEYS = ("segments", "sources", "kind", "level", "lang", "mode", "quote_check", "notices", "suggest_daai", "ocr")
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _history(db: Session, sid: str, conversation_id: int) -> list[dict]:
    """The model sees only this conversation's last turns: a new conversation starts with no context."""
    out = []
    for turn in recent_turns(db, sid, limit=4, conversation_id=conversation_id):
        out.append({"role": "user", "text": turn.question})
        out.append({"role": "assistant", "text": plain_text(turn.answer)})
    return out


def _conversation(db: Session, sid: str, cid: int | None) -> Conversation | None:
    conv = db.get(Conversation, cid) if cid else None
    return conv if conv and conv.session_id == sid else None


@router.post("/ask")
def ask_question(question: str = Form(""), lang: str = Form("ar"), image: UploadFile | None = File(None),
                 conversation_id: int | None = Form(None),
                 me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    """Answers in the given conversation, or starts a new one (also when the id isn't this seeker's,
    e.g. a chat from before signing out)."""
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
    conv = _conversation(db, me.id, conversation_id)
    history = _history(db, me.id, conv.id) if conv else []
    result = ask(AskContext(question=question, ui_lang="ar" if lang == "ar" else "en",
                            history=history, image=data, image_type=media_type))
    if conv is None:
        conv = Conversation(session_id=me.id, title=title_for(question))
        db.add(conv)
        db.flush()
    elif not conv.title and question.strip():
        conv.title = title_for(question)   # the chat began with a photo only
    conv.updated_at = utcnow()
    turn = ChatTurn(session_id=me.id, conversation_id=conv.id, question=question.strip()[:2000] or "(image)",
                    lang=result["lang"], level=result.get("level", "A"), kind=result["kind"], mode=result["mode"],
                    answer={k: result.get(k) for k in SAVED_KEYS})
    db.add(turn)
    db.commit()
    return {"turn_id": turn.id, "conversation_id": conv.id, **result,
            "trace": public_trace(result.get("trace") or {})}


def public_trace(trace: dict) -> dict:
    """What the "How I found this" sheet needs. Text the pipeline removed (uncited sentences, unverified
    quotes, verses the model typed) stays on the server: counts only. SABEELI_DEBUG_TRACE=1 keeps it all."""
    if os.getenv("SABEELI_DEBUG_TRACE") == "1":
        return trace
    out = dict(trace)
    for k in ("removed_uncited", "unverified_quotes", "scripture_guard", "uncited"):
        if k in out:
            out[k] = len(out[k]) if isinstance(out[k], list) else out[k]
    return out


def turn_view(turn: ChatTurn) -> dict:
    """A saved turn as the Ask page shows it again. Source cards are rebuilt from the corpus."""
    corpus = get_corpus()
    ans = dict(turn.answer or {})
    lang = ans.get("lang") or turn.lang
    ans["cards"] = {pid: corpus.get(pid).card(lang) for pid in ans.get("sources") or [] if corpus.get(pid)}
    return {"turn_id": turn.id, "conversation_id": turn.conversation_id,
            "question": "" if turn.question == "(image)" else turn.question,
            "had_image": turn.question == "(image)", "created_at": iso(turn.created_at),
            "helpful": turn.helpful, "answer": {**ans, "turn_id": turn.id, "conversation_id": turn.conversation_id}}


def _saved(db: Session, sid: str) -> bool:
    """Signed in: chats are kept on the account. Anonymous: they follow the normal retention."""
    accounts = account_session_ids().subquery()
    return db.scalar(select(accounts.c.session_id).where(accounts.c.session_id == sid)) is not None


@router.get("/conversations")
def conversations(me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    """This seeker's chats, most recently used first."""
    purge_expired(db)
    adopt_loose_turns(db, me.id)
    counts = dict(db.execute(select(ChatTurn.conversation_id, func.count(ChatTurn.id))
                             .where(ChatTurn.session_id == me.id).group_by(ChatTurn.conversation_id)).all())
    rows = db.scalars(select(Conversation).where(Conversation.session_id == me.id)
                      .order_by(Conversation.updated_at.desc(), Conversation.id.desc())).all()
    return {"saved": _saved(db, me.id),
            "conversations": [{"id": c.id, "title": c.title, "created_at": iso(c.created_at),
                               "updated_at": iso(c.updated_at), "turns": counts.get(c.id, 0)}
                              for c in rows if counts.get(c.id)]}


@router.get("/conversations/{cid}")
def conversation(cid: int, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    purge_expired(db)
    conv = _conversation(db, me.id, cid)
    if not conv:
        raise HTTPException(404, "not found")
    turns = recent_turns(db, me.id, limit=500, conversation_id=conv.id)
    return {"id": conv.id, "title": conv.title, "created_at": iso(conv.created_at),
            "updated_at": iso(conv.updated_at), "turns": [turn_view(t) for t in turns]}


@router.delete("/conversations/{cid}")
def delete_conversation(cid: int, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    """Deletes one chat (on every device, when signed in)."""
    conv = _conversation(db, me.id, cid)
    if not conv:
        raise HTTPException(404, "not found")
    db.execute(delete(ChatTurn).where(ChatTurn.conversation_id == conv.id, ChatTurn.session_id == me.id))
    db.delete(conv)
    db.commit()
    return {"ok": True}


@router.get("/ask/history")
def ask_history(limit: int = 50, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    """This seeker's latest questions and answers across all chats, oldest first. `saved` says whether they
    are kept (signed in) or follow the normal retention (anonymous)."""
    purge_expired(db)
    turns = recent_turns(db, me.id, limit=max(1, min(limit, 200)), recent_only=False)
    return {"saved": _saved(db, me.id), "turns": [turn_view(t) for t in turns]}


@router.delete("/ask/history")
def clear_history(me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    """Deletes all of this seeker's chats (on every device, when signed in)."""
    db.execute(delete(ChatTurn).where(ChatTurn.session_id == me.id))
    db.execute(delete(Conversation).where(Conversation.session_id == me.id))
    db.commit()
    return {"ok": True}


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
    from .embeddings import status
    return {**get_corpus().stats(), "semantic_search": status()}
