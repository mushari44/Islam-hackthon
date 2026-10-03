"""RAG tables. Owner: Mushari."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, delete, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from ...core.config import settings
from ...core.db import Base, on_session_delete, utcnow
from ..auth.public import account_session_ids


class ChatTurn(Base):
    """One question and its answer. Anonymous turns are deleted after RETENTION_HOURS; a signed-in
    seeker's turns are filed under their account's session and kept until they clear them or delete the account."""
    __tablename__ = "chat_turn"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    question: Mapped[str] = mapped_column(Text)
    lang: Mapped[str] = mapped_column(String(8), default="ar")
    level: Mapped[str] = mapped_column(String(1), default="A")
    kind: Mapped[str] = mapped_column(String(24), default="answer")
    mode: Mapped[str] = mapped_column(String(16), default="ai")
    answer: Mapped[dict] = mapped_column(JSON, default=dict)
    helpful: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    feedback_reason: Mapped[str] = mapped_column(String(64), default="")


def recent_turns(db: Session, session_id: str, limit: int = 6, recent_only: bool = True) -> list[ChatTurn]:
    """Oldest first. Used by the referral card (features/calls) as well as for follow-up questions.

    `recent_only` keeps to the last RETENTION_HOURS, so a signed-in seeker's saved chats from earlier days
    don't leak into a new question's context or referral card. The history screen passes False."""
    q = select(ChatTurn).where(ChatTurn.session_id == session_id)
    if recent_only:
        q = q.where(ChatTurn.created_at >= utcnow() - timedelta(hours=settings.retention_hours))
    rows = db.scalars(q.order_by(ChatTurn.id.desc()).limit(limit)).all()
    return list(reversed(rows))


def purge_expired(db: Session) -> None:
    cutoff = utcnow() - timedelta(hours=settings.retention_hours)
    db.execute(delete(ChatTurn).where(ChatTurn.created_at < cutoff, ChatTurn.session_id.not_in(account_session_ids())))
    db.commit()


@on_session_delete
def _purge_session(db: Session, sid: str) -> None:
    db.execute(delete(ChatTurn).where(ChatTurn.session_id == sid))
