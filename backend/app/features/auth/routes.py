"""Auth API: anonymous seeker sessions, "delete my data", da'i login, profile and availability. Owner: Eman."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...core.db import SESSION_PURGERS, get_db
from .deps import daai, seeker
from .models import Daai, SeekerSession
from .security import hash_password, new_seeker_token, seeker_id, sign, verify_password

router = APIRouter(prefix="/api")


@router.post("/session")
def new_session(db: Session = Depends(get_db)):
    token = new_seeker_token()
    db.add(SeekerSession(id=seeker_id(token)))
    db.commit()
    return {"token": token}


@router.delete("/me")
def delete_my_data(me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    """Removes everything tied to this browser session, across all features."""
    for purge in SESSION_PURGERS:
        purge(db, me.id)
    db.delete(me)
    db.commit()
    return {"ok": True}


class LoginIn(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=200)


@router.post("/daai/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(Daai).filter(Daai.username == body.username.strip().lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "wrong username or password")
    return {"token": sign({"kind": "daai", "id": user.id}), "me": profile(user)}


def profile(user: Daai) -> dict:
    return {"id": user.id, "username": user.username, "name": user.display_name, "name_en": user.display_name_en,
            "gender": user.gender, "languages": user.languages or [], "role": user.role,
            "available": user.available, "bio": user.bio, "bio_en": user.bio_en, "is_demo": user.is_demo}


@router.get("/daai/me")
def me(user: Daai = Depends(daai)):
    return profile(user)


class AvailabilityIn(BaseModel):
    available: bool


@router.post("/daai/availability")
def set_availability(body: AvailabilityIn, user: Daai = Depends(daai), db: Session = Depends(get_db)):
    user.available = body.available
    db.commit()
    return profile(user)


def create_daai(db: Session, username: str, password: str, **fields) -> Daai:
    user = Daai(username=username.lower(), password_hash=hash_password(password), **fields)
    db.add(user)
    db.flush()
    return user
