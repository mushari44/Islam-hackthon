"""Calls and referral tables. Owner: Eman."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, delete, select, update
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
    # Last time the seeker's waiting screen polled this request. A request whose seeker closed the tab stops
    # being refreshed, so the da'i's queue can drop it instead of offering a call nobody will answer.
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=utcnow)
    # When the call room last became empty (signalling.py), so an accepted call both people left can be closed.
    room_empty_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CallMessage(Base):
    """Text chat inside a call room (also the fallback when audio can't connect)."""
    __tablename__ = "call_message"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("call_request.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sender: Mapped[str] = mapped_column(String(8))  # seeker | daai
    text: Mapped[str] = mapped_column(Text)


class DaaiSchedule(Base):
    """A da'i's weekly hours for booked calls, in their own time zone (so summer time is handled).

    `weekly` maps a weekday ("sun".."sat") to [["18:00", "21:00"], ...] wall-clock ranges on the half hour;
    `days_off` lists ISO dates with no bookings; `paused` hides every future slot without touching bookings."""
    __tablename__ = "daai_schedule"
    daai_id: Mapped[int] = mapped_column(ForeignKey("daai.id", ondelete="CASCADE"), primary_key=True)
    tz: Mapped[str] = mapped_column(String(64), default="Asia/Riyadh")
    weekly: Mapped[dict] = mapped_column(JSON, default=dict)
    days_off: Mapped[list] = mapped_column(JSON, default=list)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Booking(Base):
    """A call a signed-in seeker booked in one of a da'i's free slots (times in UTC).

    status: booked -> done (the call ended) | cancelled (cancelled_by seeker|daai|system; rescheduled_to when the
    seeker moved it) | missed (missed_by seeker|daai|both). The call itself is an ordinary CallRequest, created
    when the da'i presses Start."""
    __tablename__ = "booking"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    daai_id: Mapped[int] = mapped_column(ForeignKey("daai.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    minutes: Mapped[int] = mapped_column(Integer, default=30)
    lang: Mapped[str] = mapped_column(String(8))
    note: Mapped[str] = mapped_column(Text, default="")             # optional topic the seeker typed for the da'i
    referral_id: Mapped[int | None] = mapped_column(ForeignKey("referral.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="booked")
    cancelled_by: Mapped[str] = mapped_column(String(8), default="")
    cancel_note: Mapped[str] = mapped_column(Text, default="")      # the da'i's short message when they cancel
    missed_by: Mapped[str] = mapped_column(String(8), default="")
    seeker_ready_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)   # pressed Join
    call_id: Mapped[int | None] = mapped_column(ForeignKey("call_request.id", ondelete="SET NULL"), nullable=True)
    rescheduled_to: Mapped[int | None] = mapped_column(Integer, nullable=True)   # the seeker moved it to this booking
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class BookingBlock(Base):
    """One taken half hour of a da'i's time. The unique key is what stops two seekers booking the same time:
    a 60-minute booking holds two blocks, and a cancelled booking gives its blocks back."""
    __tablename__ = "booking_block"
    __table_args__ = (UniqueConstraint("daai_id", "starts_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    daai_id: Mapped[int] = mapped_column(Integer, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    booking_id: Mapped[int] = mapped_column(ForeignKey("booking.id", ondelete="CASCADE"), index=True)


@on_session_delete
def _purge_session(db: Session, sid: str) -> None:
    bookings = db.scalars(select(Booking.id).where(Booking.session_id == sid)).all()
    if bookings:
        db.execute(delete(BookingBlock).where(BookingBlock.booking_id.in_(bookings)))
        db.execute(delete(Booking).where(Booking.id.in_(bookings)))
    calls = db.scalars(select(CallRequest.id).where(CallRequest.session_id == sid)).all()
    if calls:
        db.execute(delete(CallMessage).where(CallMessage.call_id.in_(calls)))
        db.execute(delete(CallRequest).where(CallRequest.id.in_(calls)))
    db.execute(delete(Referral).where(Referral.session_id == sid))


@on_session_merge
def _merge_session(db: Session, from_sid: str, to_sid: str) -> None:
    db.execute(update(CallRequest).where(CallRequest.session_id == from_sid).values(session_id=to_sid))
    db.execute(update(Referral).where(Referral.session_id == from_sid).values(session_id=to_sid))
    db.execute(update(Booking).where(Booking.session_id == from_sid).values(session_id=to_sid))
