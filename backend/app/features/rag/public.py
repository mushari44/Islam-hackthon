"""What other features may use from RAG. Owner: Mushari.

features/calls (the referral card, the da'i's view of cited sources) and
features/community (the @سبيلي assistant in groups) import only from here, so
the RAG internals can change freely as long as these functions keep working.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .corpus import get_corpus
from .models import ChatTurn, Conversation, recent_turns
from .pipeline import AskContext, ask, plain_text
from .routes import turn_view


SMALL_TALK = {"greeting", "thanks", "off_topic", "empty"}


def _question_turns(db: Session, session_id: str, limit: int, conversation_id: int | None = None):
    turns = recent_turns(db, session_id, limit, conversation_id=conversation_id)
    return [t for t in turns if t.kind not in SMALL_TALK]


def conversation_transcript(db: Session, session_id: str, limit: int = 6, conversation_id: int | None = None) -> str:
    """The seeker's recent questions and answers, with the source ids each answer cited. With
    `conversation_id`, only that chat's (the one the seeker pressed "Talk to a da'i" in)."""
    return "\n".join(f"User: {t.question}\nSabeeli: {plain_text(t.answer)[:900]}"
                     for t in _question_turns(db, session_id, limit, conversation_id))


def last_question(db: Session, session_id: str, conversation_id: int | None = None) -> tuple[str, list[str]]:
    """The latest real question (not small talk) and the sources its answer used."""
    turns = _question_turns(db, session_id, 6, conversation_id)
    if not turns:
        return "", []
    return turns[-1].question, list(turns[-1].answer.get("sources") or [])


def owns_conversation(db: Session, session_id: str, conversation_id: int | None) -> bool:
    conv = db.get(Conversation, conversation_id) if conversation_id else None
    return bool(conv and conv.session_id == session_id)


def conversation_size(db: Session, session_id: str, conversation_id: int) -> tuple[int, int | None]:
    """(number of turns, id of the latest turn) in one of this seeker's conversations."""
    n, last = db.execute(select(func.count(ChatTurn.id), func.max(ChatTurn.id)).where(
        ChatTurn.session_id == session_id, ChatTurn.conversation_id == conversation_id)).one()
    return n, last


def shared_conversation(db: Session, session_id: str, conversation_id: int, upto_turn_id: int) -> list[dict]:
    """The turns of a conversation the seeker chose to share with a da'i, as the Ask page shows them (questions,
    cited answers, source cards), up to the turn that was latest when they shared it. Empty once they delete it."""
    turns = db.scalars(select(ChatTurn).where(ChatTurn.session_id == session_id,
                                              ChatTurn.conversation_id == conversation_id,
                                              ChatTurn.id <= upto_turn_id).order_by(ChatTurn.id).limit(100)).all()
    keep = ("question", "had_image", "created_at", "answer")
    return [{k: v for k, v in turn_view(t).items() if k in keep} for t in turns]


def source_exists(pid: str) -> bool:
    return get_corpus().get(pid) is not None


def source_card(pid: str, lang: str) -> dict | None:
    p = get_corpus().get(pid)
    return p.card(lang) if p else None


def answer_in_group(question: str, lang: str) -> dict:
    """A short cited answer for the group assistant (no history, shorter text)."""
    return ask(AskContext(question=question, ui_lang=lang, surface="group", max_words=120))


def semantic_status() -> str:
    """"loading" while the E5 encoder is still being loaded at start-up; otherwise on/off and why."""
    from .embeddings import status
    return status()


def semantic_encoder():
    """The multilingual E5 encoder RAG search uses, or None when semantic search is off, not built or
    still loading. Other features (the videos page's related videos) embed their own text with it, so a
    question and a video title are compared in the same space. Never blocks."""
    from .embeddings import encoder
    return encoder()
