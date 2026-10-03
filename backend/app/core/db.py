"""Database engine, session and the models every feature shares.

Feature tables live next to their feature (features/*/models.py) on the same
Base; accounts and sessions are in features/auth/models.py. SQLite locally;
any SQLAlchemy URL (e.g. PostgreSQL) in deployment.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import JSON, String, create_engine, event, inspect, text
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
    add_missing_columns()


def add_missing_columns() -> list[str]:
    """Adds columns that models gained since the database was created.

    create_all() makes new tables but never changes existing ones, so a new column would otherwise
    break every copy of the app until its database is deleted. Only additive changes are handled (new
    columns and their indexes): renames, drops and type changes still need a manual step. Returns
    "table.column" for each column added.
    """
    added = []
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in tables:
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col.type.compile(engine.dialect)}'
                default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
                if isinstance(default, bool):
                    ddl += f" DEFAULT {int(default) if engine.dialect.name == 'sqlite' else str(default).upper()}"
                elif isinstance(default, (int, float)):
                    ddl += f" DEFAULT {default}"
                elif isinstance(default, str):
                    ddl += " DEFAULT '" + default.replace("'", "''") + "'"
                conn.execute(text(ddl))
                added.append(f"{table.name}.{col.name}")
            for index in table.indexes:   # e.g. the index on a column added above
                index.create(conn, checkfirst=True)
    return added


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


# When a browser signs in to an account, what it did before signing in (chats, calls, RSVPs) moves to the
# account, so it isn't left behind on that one device. Each feature registers how: fn(db, from_sid, to_sid).
SESSION_MERGERS: list[Callable[[Session, str, str], None]] = []


def on_session_merge(fn: Callable[[Session, str, str], None]) -> Callable[[Session, str, str], None]:
    SESSION_MERGERS.append(fn)
    return fn
