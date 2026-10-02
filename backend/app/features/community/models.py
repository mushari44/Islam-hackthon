"""Community tables: da'i-led groups and in-person meetups. Owner: Mushari."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, delete, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from ...core.db import Base, on_session_delete, utcnow


class Group(Base):
    __tablename__ = "study_group"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    lang: Mapped[str] = mapped_column(String(8), default="ar")
    country: Mapped[str] = mapped_column(String(64), default="")
    city: Mapped[str] = mapped_column(String(64), default="")
    audience: Mapped[str] = mapped_column(String(16), default="all")   # all | women | men
    leader_id: Mapped[int] = mapped_column(ForeignKey("daai.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class GroupMember(Base):
    __tablename__ = "group_member"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("study_group.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    nickname: Mapped[str] = mapped_column(String(40))
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    muted: Mapped[bool] = mapped_column(Boolean, default=False)
    strikes: Mapped[int] = mapped_column(Integer, default=0)
    last_post_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    left: Mapped[bool] = mapped_column(Boolean, default=False)


class GroupMessage(Base):
    __tablename__ = "group_message"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("study_group.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    author_type: Mapped[str] = mapped_column(String(8))   # seeker | daai | bot | system
    author_name: Mapped[str] = mapped_column(String(120))
    member_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daai_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)   # assistant answers: segments + cards
    reply_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_leader: Mapped[bool] = mapped_column(Boolean, default=False)   # the assistant asks the leader to step in


class Meetup(Base):
    __tablename__ = "meetup"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    lang: Mapped[str] = mapped_column(String(8), default="ar")
    country: Mapped[str] = mapped_column(String(64), default="")
    city: Mapped[str] = mapped_column(String(64), default="")
    venue: Mapped[str] = mapped_column(String(200), default="")      # a public place only
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    duration_min: Mapped[int] = mapped_column(Integer, default=90)
    capacity: Mapped[int] = mapped_column(Integer, default=20)
    audience: Mapped[str] = mapped_column(String(16), default="all")  # all | women | men | families
    host_id: Mapped[int] = mapped_column(ForeignKey("daai.id"))
    group_id: Mapped[int | None] = mapped_column(ForeignKey("study_group.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open")   # open | cancelled
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class RSVP(Base):
    __tablename__ = "rsvp"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meetup_id: Mapped[int] = mapped_column(ForeignKey("meetup.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    nickname: Mapped[str] = mapped_column(String(40))
    code: Mapped[str] = mapped_column(String(16), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)


@on_session_delete
def _purge_session(db: Session, sid: str) -> None:
    db.execute(delete(RSVP).where(RSVP.session_id == sid))
    # Group posts stay readable for others, but are no longer linked to the browser.
    for m in db.scalars(select(GroupMember).where(GroupMember.session_id == sid)).all():
        m.session_id, m.left = "deleted", True
