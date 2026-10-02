"""Request dependencies: anonymous seeker sessions and signed da'i tokens."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .db import Daai, SeekerSession, get_db, utcnow
from .security import seeker_id, unsign


def seeker(x_seeker: str = Header(default=""), db: Session = Depends(get_db)) -> SeekerSession:
    if len(x_seeker) < 20:
        raise HTTPException(401, "no session")
    sid = seeker_id(x_seeker)
    row = db.get(SeekerSession, sid)
    if not row:
        raise HTTPException(401, "unknown session")
    row.last_seen = utcnow()
    db.commit()
    return row


def optional_seeker(x_seeker: str = Header(default=""), db: Session = Depends(get_db)) -> SeekerSession | None:
    if len(x_seeker) < 20:
        return None
    return db.get(SeekerSession, seeker_id(x_seeker))


def daai_from_token(token: str, db: Session) -> Daai | None:
    body = unsign(token or "")
    if not body or body.get("kind") != "daai":
        return None
    return db.get(Daai, body.get("id"))


def daai(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> Daai:
    token = authorization.removeprefix("Bearer ").strip()
    user = daai_from_token(token, db)
    if not user:
        raise HTTPException(401, "login required")
    user.last_seen = utcnow()
    db.commit()
    return user


def optional_daai(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> Daai | None:
    token = authorization.removeprefix("Bearer ").strip()
    return daai_from_token(token, db) if token else None


def admin(user: Daai = Depends(daai)) -> Daai:
    if user.role != "admin":
        raise HTTPException(403, "admin only")
    return user
