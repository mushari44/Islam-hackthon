"""Request dependencies: seeker sessions (with optional accounts) and signed da'i tokens. Owner: Eman."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
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


def signed_out_home(db: Session, row: SeekerSession | None) -> bool:
    """True for the browser that created an account and then signed out of it.

    That browser's session is the account's home, where every feature files the account's data, so the
    token must stop working after sign-out: otherwise the next person on that device would see the
    account's chats and bookings. The web client answers a 401 by starting a fresh anonymous session."""
    return bool(row and row.account_id is None
                and db.scalar(select(SeekerAccount.id).where(SeekerAccount.session_id == row.id)) is not None)


def seeker_device(x_seeker: str = Header(default=""), db: Session = Depends(get_db)) -> SeekerSession:
    """This browser's own session row (used to sign in and out)."""
    if len(x_seeker) < 20:
        raise HTTPException(401, "no session")
    row = db.get(SeekerSession, seeker_id(x_seeker))
    if not row or signed_out_home(db, row):
        raise HTTPException(401, "unknown session")
    row.last_seen = utcnow()
    db.commit()
    return row


def seeker(device: SeekerSession = Depends(seeker_device), db: Session = Depends(get_db)) -> SeekerSession:
    return canonical(db, device)


def optional_seeker(x_seeker: str = Header(default=""), db: Session = Depends(get_db)) -> SeekerSession | None:
    if len(x_seeker) < 20:
        return None
    row = db.get(SeekerSession, seeker_id(x_seeker))
    return None if signed_out_home(db, row) else canonical(db, row)


def seeker_key(db: Session, token: str) -> str | None:
    """The session id a seeker token files data under (for the call room, which has no request headers)."""
    device = db.get(SeekerSession, seeker_id(token or ""))
    row = None if signed_out_home(db, device) else canonical(db, device)
    return row.id if row else None


def daai_from_token(token: str, db: Session) -> Daai | None:
    body = unsign(token or "")
    if not body or body.get("kind") != "daai":
        return None
    user = db.get(Daai, body.get("id"))
    if not user or user.active is False or body.get("v", 0) != (user.token_version or 0):
        return None
    return user


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
