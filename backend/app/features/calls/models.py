"""Calls and referral tables. Owner: Eman."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, delete, select, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from ...core.db import Base, on_session_delete, on_session_merge, utcnow


class Referral(Base):
    """The card a seeker reviews, edits and (only if they consent) shares with a da'i."""
    __tablename__ = "referral"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    mode: Mapped[str] = mapped_column(String(16), default="model")   # model | template | none (experiment arm)
    proposed: Mapped[dict] = mapped_column(JSON, default=dict)
    final: Mapped[dict] = mapped_column(JSON, default=dict)
    consented: Mapped[bool] = mapped_column(Boolean, default=False)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    lang: Mapped[str] = mapped_column(String(8), default="ar")
    # The Ask conversation the card was drafted from (rag's Conversation.id), so the seeker's chat list can
    # show which da'i they talked to about it. NULL when the call started from the Talk page.
    conversation_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # The seeker also agreed to share that conversation's messages (up to `chat_upto`, the latest turn id when
    # they agreed) with the da'i who takes the call. Separate from `consented`, which covers the card.
    share_chat: Mapped[bool] = mapped_column(Boolean, default=False)
    chat_upto: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CallRequest(Base):
    __tablename__ = "call_request"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    lang: Mapped[str] = mapped_column(String(8))
    gender_pref: Mapped[str] = mapped_column(String(1), default="")   # "", m, f
    referral_id: Mapped[int | None] = mapped_column(ForeignKey("referral.id", ondelete="SET NULL"), nullable=True)
    # Set when the seeker asked for one da'i by name (from the directory or "call again"): only that da'i sees it.
    daai_pref: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="waiting")  # waiting|accepted|ended|cancelled|expired
    daai_id: Mapped[int | None] = mapped_column(ForeignKey("daai.id"), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Measurements for the referral experiment, filled in by the da'i.
    card_opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    understood_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reexplain_needed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    card_accurate: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    daai_note: Mapped[str] = mapped_column(Text, default="")
    seeker_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CallMessage(Base):
    """Text chat inside a call room (also the fallback when audio can't connect)."""
    __tablename__ = "call_message"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("call_request.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sender: Mapped[str] = mapped_column(String(8))  # seeker | daai
    text: Mapped[str] = mapped_column(Text)


@on_session_delete
def _purge_session(db: Session, sid: str) -> None:
    calls = db.scalars(select(CallRequest.id).where(CallRequest.session_id == sid)).all()
    if calls:
        db.execute(delete(CallMessage).where(CallMessage.call_id.in_(calls)))
        db.execute(delete(CallRequest).where(CallRequest.id.in_(calls)))
    db.execute(delete(Referral).where(Referral.session_id == sid))


@on_session_merge
def _merge_session(db: Session, from_sid: str, to_sid: str) -> None:
    db.execute(update(CallRequest).where(CallRequest.session_id == from_sid).values(session_id=to_sid))
    db.execute(update(Referral).where(Referral.session_id == from_sid).values(session_id=to_sid))
