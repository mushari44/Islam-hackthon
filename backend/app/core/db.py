"""Database engine, session and the models every feature shares.

Feature tables live next to their feature (features/*/models.py) on the same
Base. SQLite locally; any SQLAlchemy URL (e.g. PostgreSQL) in deployment.

Seekers have no accounts: a random session token kept in the browser is all
that links their questions, referrals, calls and RSVPs.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


class Base(DeclarativeBase):
    pass


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


class Setting(Base):
    """Small key/value store (e.g. the referral experiment's arm counter)."""
    __tablename__ = "app_setting"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args, pool_pre_ping=True)

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Each feature registers how to erase a seeker's data, so "delete my data"
# (core/accounts.py) never needs to know about feature tables.
SESSION_PURGERS: list[Callable[[Session, str], None]] = []


def on_session_delete(fn: Callable[[Session, str], None]) -> Callable[[Session, str], None]:
    SESSION_PURGERS.append(fn)
    return fn
