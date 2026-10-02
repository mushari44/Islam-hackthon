"""Database engine, session and the models every feature shares.

Feature tables live next to their feature (features/*/models.py) on the same
Base; accounts and sessions are in features/auth/models.py. SQLite locally;
any SQLAlchemy URL (e.g. PostgreSQL) in deployment.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import JSON, String, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


class Base(DeclarativeBase):
    pass


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
# (features/auth/routes.py) never needs to know about other features' tables.
SESSION_PURGERS: list[Callable[[Session, str], None]] = []


def on_session_delete(fn: Callable[[Session, str], None]) -> Callable[[Session, str], None]:
    SESSION_PURGERS.append(fn)
    return fn
