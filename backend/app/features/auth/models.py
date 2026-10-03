"""Accounts and sessions. Owner: Eman.

A seeker starts with no account: a random session token kept in the browser links
their questions, referrals, calls and RSVPs. They may add an optional account
(a username and password, nothing else that identifies them) to keep that history
on any device: each browser session then points at the account's own session, so
every feature keeps using one session id. Da'is (and the reviewer) sign in with a
username and password.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
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
    country: Mapped[str] = mapped_column(String(2), default="")       # where the da'i is based, shown to seekers
    city: Mapped[str] = mapped_column(String(64), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)      # the reviewer can disable an account
    token_version: Mapped[int] = mapped_column(Integer, default=0)   # bumped on a password reset: old tokens stop working
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    def public(self, lang: str = "ar") -> dict:
        return {"id": self.id, "name": self.display_name if lang == "ar" else (self.display_name_en or self.display_name),
                "gender": self.gender, "languages": self.languages or [], "country": self.country or "",
                "city": self.city or ""}


class SeekerAccount(Base):
    """Optional seeker account: a username and a password, and an optional email for password resets.

    The seeker may also give a language, country, city, age band and sex, at sign-up or later. Each one is
    optional and defaults to "not given" (language defaults to Arabic). No real name, phone or birth date."""
    __tablename__ = "seeker_account"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(32))
    username_key: Mapped[str] = mapped_column(String(32), unique=True)   # lower-cased, for lookups
    password_hash: Mapped[str] = mapped_column(String(256))
    recovery_hash: Mapped[str] = mapped_column(String(256))             # one-time code shown at sign-up
    email: Mapped[str] = mapped_column(String(254), default="")         # optional, only to reset a forgotten password
    reset_hash: Mapped[str] = mapped_column(String(256), default="")    # emailed 6-digit code, hashed
    reset_expires: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    session_id: Mapped[str] = mapped_column(String(64))                 # the session all features file data under
    country: Mapped[str] = mapped_column(String(2), default="")         # optional, for nearby groups and events
    city: Mapped[str] = mapped_column(String(64), default="")
    lang: Mapped[str] = mapped_column(String(8), default="ar")             # interface and call language: ar | en
    # Optional age band (never a birth date), so meetups and groups for an age can be suggested.
    age_band: Mapped[str] = mapped_column(String(8), default="")
    gender: Mapped[str] = mapped_column(String(1), default="")              # optional: m | f | "" (not given)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SeekerSession(Base):
    __tablename__ = "seeker_session"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)    # sha256 of the browser token
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # Set while this browser is signed in to an account.
    account_id: Mapped[int | None] = mapped_column(ForeignKey("seeker_account.id", ondelete="SET NULL"), nullable=True)
