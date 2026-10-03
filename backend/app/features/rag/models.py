"""RAG tables. Owner: Mushari."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, delete, exists, select, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from ...core.config import settings
from ...core.db import Base, on_session_delete, on_session_merge, utcnow
from ..auth.public import account_session_ids


class Conversation(Base):
    """One chat on the Ask page. "New conversation" starts another one and keeps this one, so a seeker can
    go back to any earlier chat. Filed under the same session as its turns (the account's, when signed in)."""
    __tablename__ = "conversation"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(120), default="")   # the first question, shortened
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class ChatTurn(Base):
    """One question and its answer. Anonymous turns are deleted after RETENTION_HOURS; a signed-in
    seeker's turns are filed under their account's session and kept until they clear them or delete the account."""
    __tablename__ = "chat_turn"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    # The conversation this turn belongs to. NULL only for turns saved before conversations existed;
    # those are gathered into one conversation the first time the seeker's chat list is read.
    conversation_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    question: Mapped[str] = mapped_column(Text)
    lang: Mapped[str] = mapped_column(String(8), default="ar")
    level: Mapped[str] = mapped_column(String(1), default="A")
    kind: Mapped[str] = mapped_column(String(24), default="answer")
    mode: Mapped[str] = mapped_column(String(16), default="ai")
    answer: Mapped[dict] = mapped_column(JSON, default=dict)
    helpful: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    feedback_reason: Mapped[str] = mapped_column(String(64), default="")


def recent_turns(db: Session, session_id: str, limit: int = 6, recent_only: bool = True,
                 conversation_id: int | None = None) -> list[ChatTurn]:
    """Oldest first. Used by the referral card (features/calls) as well as for follow-up questions.

    With `conversation_id`, only that conversation's turns (and only if it is this session's). Without it,
    `recent_only` keeps to the last RETENTION_HOURS, so a signed-in seeker's saved chats from earlier days
    don't leak into a referral card. The history screens pass False."""
    q = select(ChatTurn).where(ChatTurn.session_id == session_id)
    if conversation_id is not None:
        q = q.where(ChatTurn.conversation_id == conversation_id)
    elif recent_only:
        q = q.where(ChatTurn.created_at >= utcnow() - timedelta(hours=settings.retention_hours))
    rows = db.scalars(q.order_by(ChatTurn.id.desc()).limit(limit)).all()
    return list(reversed(rows))


def title_for(question: str) -> str:
    q = " ".join(question.split())
    return q if len(q) <= 80 else q[:79].rstrip() + "…"


def adopt_loose_turns(db: Session, session_id: str) -> None:
    """Gathers turns saved before conversations existed into one conversation, so they show in the list."""
    loose = db.scalars(select(ChatTurn).where(ChatTurn.session_id == session_id, ChatTurn.conversation_id.is_(None))
                       .order_by(ChatTurn.id)).all()
    if not loose:
        return
    first = next((t.question for t in loose if t.question != "(image)"), "")
    conv = Conversation(session_id=session_id, title=title_for(first), created_at=loose[0].created_at,
                        updated_at=loose[-1].created_at)
    db.add(conv)
    db.flush()
    for t in loose:
        t.conversation_id = conv.id
    db.commit()


def purge_expired(db: Session) -> None:
    """Anonymous turns older than RETENTION_HOURS go, and so does any conversation left with no turns."""
    cutoff = utcnow() - timedelta(hours=settings.retention_hours)
    db.execute(delete(ChatTurn).where(ChatTurn.created_at < cutoff, ChatTurn.session_id.not_in(account_session_ids())))
    db.execute(delete(Conversation).where(Conversation.updated_at < cutoff,
                                          ~exists().where(ChatTurn.conversation_id == Conversation.id)))
    db.commit()


@on_session_delete
def _purge_session(db: Session, sid: str) -> None:
    db.execute(delete(ChatTurn).where(ChatTurn.session_id == sid))
    db.execute(delete(Conversation).where(Conversation.session_id == sid))


@on_session_merge
def _merge_session(db: Session, from_sid: str, to_sid: str) -> None:
    db.execute(update(ChatTurn).where(ChatTurn.session_id == from_sid).values(session_id=to_sid))
    db.execute(update(Conversation).where(Conversation.session_id == from_sid).values(session_id=to_sid))
