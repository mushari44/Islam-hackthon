"""Request dependencies: seeker sessions (with optional accounts) and signed da'i tokens. Owner: Eman."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ...core.db import get_db, utcnow
from .models import Daai, SeekerAccount, SeekerSession
from .security import seeker_id, unsign


def canonical(db: Session, row: SeekerSession | None) -> SeekerSession | None:
    """A browser signed in to an account files everything under the account's own session."""
    if row is None or row.account_id is None:
        return row
    acc = db.get(SeekerAccount, row.account_id)
    return (db.get(SeekerSession, acc.session_id) if acc else None) or row


def seeker_device(x_seeker: str = Header(default=""), db: Session = Depends(get_db)) -> SeekerSession:
    """This browser's own session row (used to sign in and out)."""
    if len(x_seeker) < 20:
        raise HTTPException(401, "no session")
    row = db.get(SeekerSession, seeker_id(x_seeker))
    if not row:
        raise HTTPException(401, "unknown session")
    row.last_seen = utcnow()
    db.commit()
    return row


def seeker(device: SeekerSession = Depends(seeker_device), db: Session = Depends(get_db)) -> SeekerSession:
    return canonical(db, device)


def optional_seeker(x_seeker: str = Header(default=""), db: Session = Depends(get_db)) -> SeekerSession | None:
    if len(x_seeker) < 20:
        return None
    return canonical(db, db.get(SeekerSession, seeker_id(x_seeker)))


def seeker_key(db: Session, token: str) -> str | None:
    """The session id a seeker token files data under (for the call room, which has no request headers)."""
    row = canonical(db, db.get(SeekerSession, seeker_id(token or "")))
    return row.id if row else None


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
