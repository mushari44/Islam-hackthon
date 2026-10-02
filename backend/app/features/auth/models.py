"""Accounts and sessions. Owner: Eman.

Seekers have no accounts: a random session token kept in the browser is all
that links their questions, referrals, calls and RSVPs. Da'is (and the
reviewer) sign in with a username and password.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ...core.db import Base, utcnow


class Daai(Base):
    """A da'i (human guide) or a reviewer. All demo accounts are synthetic."""
    __tablename__ = "daai"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    display_name_en: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(256))
    gender: Mapped[str] = mapped_column(String(1), default="m")      # m | f
    languages: Mapped[list] = mapped_column(JSON, default=list)     # ["ar", "en", ...]
    bio: Mapped[str] = mapped_column(Text, default="")
    bio_en: Mapped[str] = mapped_column(Text, default="")
    role: Mapped[str] = mapped_column(String(16), default="daai")   # daai | admin
    available: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    def public(self, lang: str = "ar") -> dict:
        return {"id": self.id, "name": self.display_name if lang == "ar" else (self.display_name_en or self.display_name),
                "gender": self.gender, "languages": self.languages or []}


class SeekerSession(Base):
    __tablename__ = "seeker_session"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)    # sha256 of the browser token
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
