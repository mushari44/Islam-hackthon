"""What other features may use from Community. Owner: Mushari.

Calls (the da'i's "became Muslim" button) records the da'i's confirmation here; the seeker then decides
in Community whether their groups hear the news.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ...core.db import Setting, utcnow
from .models import GroupMessage, NewMuslim

_COUNT_KEY = "new_muslims"
# A da'i's confirmation the seeker never answers is deleted after this long (CLAUDE.md section 3), so nothing
# about someone's religion stays on file without their own yes. The anonymous count keeps it.
PENDING_DAYS = 7


def expire_pending(db: Session) -> None:
    db.execute(delete(NewMuslim).where(NewMuslim.status == "pending",
                                       NewMuslim.created_at < utcnow() - timedelta(days=PENDING_DAYS)))
    db.commit()


def _bump_count(db: Session, by: int) -> None:
    """An anonymous running total (no session, call or da'i), so the project can report how many people
    embraced Islam through Sabeeli without keeping who they were."""
    row = db.get(Setting, _COUNT_KEY)
    if row is None:
        db.add(Setting(key=_COUNT_KEY, value={"count": max(0, by)}))
    else:
        row.value = {**row.value, "count": max(0, int(row.value.get("count", 0)) + by)}


def new_muslim_total(db: Session) -> int:
    row = db.get(Setting, _COUNT_KEY)
    return int(row.value.get("count", 0)) if row else 0


def mark_new_muslim(db: Session, sid: str, call_id: int, daai_id: int) -> str:
    """The da'i confirmed it. Returns the record's status: "pending" until the seeker answers, "shared" if they
    already agreed (after an earlier call)."""
    expire_pending(db)
    row = db.scalars(select(NewMuslim).where(NewMuslim.session_id == sid)).first()
    if row is None:
        row = NewMuslim(session_id=sid, call_id=call_id, daai_id=daai_id)
        db.add(row)
        _bump_count(db, 1)
    db.commit()
    return row.status


def unmark_new_muslim(db: Session, call_id: int, daai_id: int) -> bool:
    """The da'i pressed it by mistake: they can take it back while the seeker hasn't answered yet."""
    row = db.scalars(select(NewMuslim).where(NewMuslim.call_id == call_id, NewMuslim.daai_id == daai_id,
                                             NewMuslim.status == "pending")).first()
    if row is None:
        return False
    db.delete(row)
    _bump_count(db, -1)
    db.commit()
    return True


def new_muslim_calls(db: Session, call_ids: list[int]) -> dict[int, str]:
    """{call_id: status} for the calls in which the da'i confirmed it (and the seeker hasn't declined)."""
    if not call_ids:
        return {}
    expire_pending(db)
    rows = db.scalars(select(NewMuslim).where(NewMuslim.call_id.in_(call_ids))).all()
    return {r.call_id: r.status for r in rows}


def remove_new_muslim(db: Session, sid: str) -> None:
    """The seeker declined or took the label back: the record and its welcome messages go."""
    row = db.scalars(select(NewMuslim).where(NewMuslim.session_id == sid)).first()
    if row is None:
        return
    for mid in row.announced or []:
        msg = db.get(GroupMessage, mid)
        if msg:
            db.delete(msg)
    db.delete(row)
    db.commit()
