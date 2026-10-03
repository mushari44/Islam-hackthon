"""Auth API: seeker sessions and optional seeker accounts, "delete my data", da'i login, profile and availability. Owner: Eman."""
from __future__ import annotations

import re
import secrets
import time
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ...core.db import SESSION_PURGERS, get_db, iso, utcnow
from . import mailer
from .deps import daai, seeker, seeker_device
from .models import Daai, SeekerAccount, SeekerSession
from .security import hash_password, new_seeker_token, seeker_id, sign, verify_password

router = APIRouter(prefix="/api")


@router.post("/session")
def new_session(db: Session = Depends(get_db)):
    token = new_seeker_token()
    db.add(SeekerSession(id=seeker_id(token)))
    db.commit()
    return {"token": token}


def _purge(db: Session, me: SeekerSession) -> None:
    """Removes everything filed under this session across all features, and its account if it has one."""
    for purge in SESSION_PURGERS:
        purge(db, me.id)
    for acc in db.scalars(select(SeekerAccount).where(SeekerAccount.session_id == me.id)).all():
        db.execute(update(SeekerSession).where(SeekerSession.account_id == acc.id).values(account_id=None))
        db.delete(acc)
    db.delete(me)
    db.commit()


@router.delete("/me")
def delete_my_data(me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    """Removes everything tied to this seeker (and their account, if signed in), across all features."""
    _purge(db, me)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Optional seeker accounts: a username and a password, nothing else that identifies the person.
# Wrong credentials answer 403, not 401: the web client treats 401 as "this browser session is gone".
# ---------------------------------------------------------------------------

USERNAME = re.compile(r"^[\w.]{3,24}$")
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
RESET_TTL = timedelta(minutes=15)
_failures: dict[str, list[float]] = {}     # username_key -> recent failed sign-in times
MAX_FAILURES, FAILURE_WINDOW = 5, 600


def _key(username: str) -> str:
    return username.strip().lower()


def _too_many(key: str) -> bool:
    now = time.time()
    recent = [t for t in _failures.get(key, []) if now - t < FAILURE_WINDOW]
    _failures[key] = recent
    return len(recent) >= MAX_FAILURES


def _failed(key: str) -> None:
    _failures.setdefault(key, []).append(time.time())


def _recovery_code() -> str:
    raw = secrets.token_hex(6).upper()
    return "-".join(raw[i:i + 4] for i in range(0, 12, 4))


def account_view(acc: SeekerAccount) -> dict:
    return {"username": acc.username, "email": acc.email, "country": acc.country, "city": acc.city, "lang": acc.lang,
            "created_at": iso(acc.created_at)}


def _clean_email(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip().lower()
    if v and (len(v) > 254 or not EMAIL.match(v)):
        raise ValueError("invalid email")
    return v


def _email_taken(db: Session, email: str, other_than: int | None = None) -> bool:
    if not email:
        return False
    q = select(SeekerAccount).where(SeekerAccount.email == email)
    return any(a.id != other_than for a in db.scalars(q).all())


def _find(db: Session, login: str) -> SeekerAccount | None:
    """An account by username or by email."""
    key = _key(login)
    col = SeekerAccount.email if "@" in key else SeekerAccount.username_key
    return db.scalars(select(SeekerAccount).where(col == key)).first()


class SignupIn(BaseModel):
    username: str = Field(max_length=24)
    password: str = Field(min_length=8, max_length=200)
    email: str = Field(default="", max_length=254)

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str | None) -> str | None:
        return _clean_email(v)

    @field_validator("username")
    @classmethod
    def valid_username(cls, v: str) -> str:
        v = v.strip()
        if not USERNAME.match(v) or v.replace(".", "").replace("_", "").isdigit():
            raise ValueError("username: 3-24 letters, digits, _ or .")
        return v


class SigninIn(BaseModel):
    username: str = Field(max_length=24)
    password: str = Field(max_length=200)


@router.get("/account")
def my_account(device: SeekerSession = Depends(seeker_device), db: Session = Depends(get_db)):
    acc = db.get(SeekerAccount, device.account_id) if device.account_id else None
    return {"account": account_view(acc) if acc else None}


@router.post("/account/signup")
def signup(body: SignupIn, device: SeekerSession = Depends(seeker_device), db: Session = Depends(get_db)):
    """Creates an account that keeps what this browser has done so far, and signs this browser in."""
    if device.account_id:
        raise HTTPException(409, "already signed in")
    key = _key(body.username)
    if db.scalars(select(SeekerAccount).where(SeekerAccount.username_key == key)).first():
        raise HTTPException(409, "username taken")
    if _email_taken(db, body.email):
        raise HTTPException(409, "email taken")
    code = _recovery_code()
    acc = SeekerAccount(username=body.username, username_key=key, password_hash=hash_password(body.password),
                        recovery_hash=hash_password(code), session_id=device.id, email=body.email)
    db.add(acc)
    db.flush()
    device.account_id = acc.id
    db.commit()
    return {"account": account_view(acc), "recovery_code": code}


@router.post("/account/signin")
def signin(body: SigninIn, device: SeekerSession = Depends(seeker_device), db: Session = Depends(get_db)):
    key = _key(body.username)
    if _too_many(key):
        raise HTTPException(429, "too many attempts")
    acc = db.scalars(select(SeekerAccount).where(SeekerAccount.username_key == key)).first()
    if not acc or not verify_password(body.password, acc.password_hash):
        _failed(key)
        raise HTTPException(403, "wrong username or password")
    _failures.pop(key, None)
    device.account_id = acc.id
    db.commit()
    return {"account": account_view(acc)}


@router.post("/account/signout")
def signout(device: SeekerSession = Depends(seeker_device), db: Session = Depends(get_db)):
    device.account_id = None
    db.commit()
    return {"ok": True}


class RecoverIn(BaseModel):
    username: str = Field(max_length=24)
    recovery_code: str = Field(max_length=32)
    new_password: str = Field(min_length=8, max_length=200)


@router.post("/account/recover")
def recover(body: RecoverIn, device: SeekerSession = Depends(seeker_device), db: Session = Depends(get_db)):
    """A forgotten password is reset with the one-time recovery code; a new code replaces it."""
    key = _key(body.username)
    if _too_many(key):
        raise HTTPException(429, "too many attempts")
    acc = db.scalars(select(SeekerAccount).where(SeekerAccount.username_key == key)).first()
    if not acc or not verify_password(body.recovery_code.strip().upper(), acc.recovery_hash):
        _failed(key)
        raise HTTPException(403, "wrong username or recovery code")
    code = _recovery_code()
    acc.password_hash, acc.recovery_hash = hash_password(body.new_password), hash_password(code)
    device.account_id = acc.id
    db.commit()
    return {"account": account_view(acc), "recovery_code": code}


def _signed_in(device: SeekerSession, db: Session) -> SeekerAccount:
    acc = db.get(SeekerAccount, device.account_id) if device.account_id else None
    if not acc:
        raise HTTPException(403, "sign in first")
    return acc


class AccountIn(BaseModel):
    country: str | None = Field(default=None, max_length=2)
    city: str | None = Field(default=None, max_length=64)
    lang: str | None = None
    email: str | None = Field(default=None, max_length=254)   # "" removes it

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str | None) -> str | None:
        return _clean_email(v)


@router.post("/account/profile")
def account_profile(body: AccountIn, device: SeekerSession = Depends(seeker_device), db: Session = Depends(get_db)):
    acc = _signed_in(device, db)
    if body.country is not None:
        acc.country = body.country.strip().upper()
        if body.city is None:
            acc.city = ""
    if body.city is not None:
        acc.city = body.city.strip()
    if body.lang is not None:
        if body.lang not in DAAI_LANGUAGES:
            raise HTTPException(400, "unsupported language")
        acc.lang = body.lang
    if body.email is not None:
        if _email_taken(db, body.email, other_than=acc.id):
            raise HTTPException(409, "email taken")
        acc.email = body.email
    db.commit()
    return {"account": account_view(acc)}


class ForgotIn(BaseModel):
    login: str = Field(max_length=254)   # username or email


@router.post("/account/forgot")
def forgot(body: ForgotIn, db: Session = Depends(get_db)):
    """Emails a 6-digit reset code when the account has an email and mail is set up.

    The answer is the same whether or not the account exists, so it can't be used to find accounts.
    `via` is "email" when mail is on, otherwise "recovery" (use the recovery code from sign-up)."""
    if not mailer.enabled():
        return {"via": "recovery"}
    acc = _find(db, body.login)
    if acc and acc.email and not _too_many(_key(acc.username)):
        code = f"{secrets.randbelow(10**6):06d}"
        acc.reset_hash, acc.reset_expires = hash_password(code), utcnow() + RESET_TTL
        db.commit()
        mailer.send(acc.email, "رمز استعادة حسابك في سَبِيلي / Your Sabeeli reset code",
                    f"رمزك: {code}\nYour code: {code}\n\n"
                    "ينتهي خلال ١٥ دقيقة. إن لم تطلبه فتجاهل هذه الرسالة.\n"
                    "It expires in 15 minutes. If you didn't ask for it, ignore this email.")
    return {"via": "email"}


class ResetIn(BaseModel):
    login: str = Field(max_length=254)
    code: str = Field(max_length=12)
    new_password: str = Field(min_length=8, max_length=200)


@router.post("/account/reset")
def reset(body: ResetIn, device: SeekerSession = Depends(seeker_device), db: Session = Depends(get_db)):
    acc = _find(db, body.login)
    key = _key(acc.username) if acc else _key(body.login)
    if _too_many(key):
        raise HTTPException(429, "too many attempts")
    ok = (acc and acc.reset_hash and acc.reset_expires and acc.reset_expires > utcnow()
          and verify_password(body.code.strip(), acc.reset_hash))
    if not ok:
        _failed(key)
        raise HTTPException(403, "wrong or expired code")
    acc.password_hash = hash_password(body.new_password)
    acc.reset_hash, acc.reset_expires = "", None
    device.account_id = acc.id
    db.commit()
    return {"account": account_view(acc)}


class PasswordIn(BaseModel):
    password: str = Field(max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


@router.post("/account/password")
def change_password(body: PasswordIn, device: SeekerSession = Depends(seeker_device), db: Session = Depends(get_db)):
    acc = _signed_in(device, db)
    if not verify_password(body.password, acc.password_hash):
        raise HTTPException(403, "wrong password")
    acc.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}


class ConfirmPasswordIn(BaseModel):
    password: str = Field(max_length=200)


@router.post("/account/delete")
def delete_account(body: ConfirmPasswordIn, device: SeekerSession = Depends(seeker_device),
                   db: Session = Depends(get_db)):
    """Deletes the account and everything filed under it, on every device."""
    acc = _signed_in(device, db)
    if not verify_password(body.password, acc.password_hash):
        raise HTTPException(403, "wrong password")
    home = db.get(SeekerSession, acc.session_id)
    if home:
        _purge(db, home)
    else:
        db.execute(update(SeekerSession).where(SeekerSession.account_id == acc.id).values(account_id=None))
        db.delete(acc)
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


# Languages a da'i can offer for now. Call matching uses them, so keep this list in step with the seeker's choices.
DAAI_LANGUAGES = ("ar", "en")


class ProfileIn(BaseModel):
    """Fields a da'i may change on their own profile. Fields left out stay as they are."""
    name: str | None = Field(default=None, max_length=120)
    name_en: str | None = Field(default=None, max_length=120)
    languages: list[str] | None = None
    bio: str | None = Field(default=None, max_length=600)
    bio_en: str | None = Field(default=None, max_length=600)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is not None and len(v.strip()) < 2:
            raise ValueError("name is too short")
        return v.strip() if v is not None else v

    @field_validator("languages")
    @classmethod
    def known_languages(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        langs = list(dict.fromkeys(x.strip().lower() for x in v))   # keep order, drop repeats
        if not langs:
            raise ValueError("choose at least one language")
        unknown = [x for x in langs if x not in DAAI_LANGUAGES]
        if unknown:
            raise ValueError(f"unsupported languages: {unknown}")
        return langs


# API field name -> column name
_PROFILE_COLUMNS = {"name": "display_name", "name_en": "display_name_en", "languages": "languages",
                    "bio": "bio", "bio_en": "bio_en"}


@router.post("/daai/profile")
def update_me(body: ProfileIn, user: Daai = Depends(daai), db: Session = Depends(get_db)):
    """Lets a da'i keep their name, languages and bio current, because seekers are matched by language."""
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        setattr(user, _PROFILE_COLUMNS[key], value.strip() if isinstance(value, str) else value)
    db.commit()
    return profile(user)


def create_daai(db: Session, username: str, password: str, **fields) -> Daai:
    user = Daai(username=username.lower(), password_hash=hash_password(password), **fields)
    db.add(user)
    db.flush()
    return user
