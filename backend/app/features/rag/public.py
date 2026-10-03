"""What other features may use from RAG. Owner: Mushari.

features/calls (the referral card, the da'i's view of cited sources) and
features/community (the @سبيلي assistant in groups) import only from here, so
the RAG internals can change freely as long as these functions keep working.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .corpus import get_corpus
from .models import recent_turns
from .pipeline import AskContext, ask, plain_text


SMALL_TALK = {"greeting", "thanks", "off_topic", "empty"}


def _question_turns(db: Session, session_id: str, limit: int):
    return [t for t in recent_turns(db, session_id, limit) if t.kind not in SMALL_TALK]


def conversation_transcript(db: Session, session_id: str, limit: int = 6) -> str:
    """The seeker's recent questions and answers, with the source ids each answer cited."""
    return "\n".join(f"User: {t.question}\nSabeeli: {plain_text(t.answer)[:900]}"
                     for t in _question_turns(db, session_id, limit))


def last_question(db: Session, session_id: str) -> tuple[str, list[str]]:
    """The latest real question (not small talk) and the sources its answer used."""
    turns = _question_turns(db, session_id, limit=6)
    if not turns:
        return "", []
    return turns[-1].question, list(turns[-1].answer.get("sources") or [])


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
