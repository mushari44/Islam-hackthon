"""Auth API: seeker sessions and optional seeker accounts, "delete my data", da'i login, profile and availability. Owner: Eman."""
from __future__ import annotations

import re
import secrets
import time
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ...core.db import SESSION_MERGERS, SESSION_PURGERS, get_db, iso, utcnow
from . import mailer
from .deps import admin, daai, seeker, seeker_device
from .models import Daai, SeekerAccount, SeekerSession
from .security import hash_password, needs_refresh, new_seeker_token, seeker_id, sign, unsign, verify_password

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
# Every account gives its sex and an age band (the seeker picks them; there is no "prefer not to say"), so groups
# and meetups for women, men or an age group can be suggested. A band, never a birth date, so the account still
# can't identify anyone. Accounts made before this have "" until their owner picks one.
AGE_BANDS = ("u18", "18_24", "25_34", "35_44", "45_54", "55p")
GENDERS = ("m", "f")
COUNTRY = re.compile(r"^[A-Z]{2}$")


def _check(value: str | None, allowed: tuple, name: str) -> str | None:
    if value is not None and value not in allowed:
        raise ValueError(f"{name} must be one of {allowed}")
    return value


def _country(value: str | None) -> str | None:
    """An ISO 3166 two-letter code, upper-cased, or "" for none."""
    if value is None:
        return value
    value = value.strip().upper()
    if value and not COUNTRY.match(value):
        raise ValueError("country must be a 2-letter code")
    return value


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
            "age_band": acc.age_band or "", "gender": acc.gender or "", "created_at": iso(acc.created_at)}


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
    """Username, password, sex and age band are required. The rest is optional, with defaults: language "ar",
    and "" (not given) for email, country and city."""
    username: str = Field(max_length=24)
    password: str = Field(min_length=8, max_length=200)
    email: str = Field(default="", max_length=254)
    lang: str = "ar"
    country: str = Field(default="", max_length=2)
    city: str = Field(default="", max_length=64)
    age_band: str
    gender: str

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str | None) -> str | None:
        return _clean_email(v)

    @field_validator("lang")
    @classmethod
    def valid_lang(cls, v: str) -> str:
        return _check(v, DAAI_LANGUAGES, "lang")

    @field_validator("country")
    @classmethod
    def valid_country(cls, v: str) -> str:
        return _country(v)

    @field_validator("age_band")
    @classmethod
    def valid_age_band(cls, v: str) -> str:
        return _check(v, AGE_BANDS, "age_band")

    @field_validator("gender")
    @classmethod
    def valid_gender(cls, v: str) -> str:
        return _check(v, GENDERS, "gender")

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
                        recovery_hash=hash_password(code), session_id=device.id, email=body.email, lang=body.lang,
                        country=body.country, city=body.city.strip() if body.country else "",
                        age_band=body.age_band, gender=body.gender)
    db.add(acc)
    db.flush()
    device.account_id = acc.id
    db.commit()
    return {"account": account_view(acc), "recovery_code": code}


def _join(db: Session, device: SeekerSession, acc: SeekerAccount) -> None:
    """Signs this browser in to the account. What it did before signing in (Ask chats, calls, RSVPs) moves
    to the account, like at sign-up, so nothing is left behind on this one device. Only an anonymous
    browser's own data moves: never another account's (a browser already signed in, or an account's home)."""
    anonymous = device.account_id is None and not db.scalars(
        select(SeekerAccount.id).where(SeekerAccount.session_id == device.id)).first()
    if anonymous and device.id != acc.session_id:
        for merge in SESSION_MERGERS:
            merge(db, device.id, acc.session_id)
    device.account_id = acc.id


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
    _join(db, device, acc)
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
    _sign_out_others(db, acc, device)
    _join(db, device, acc)
    db.commit()
    return {"account": account_view(acc), "recovery_code": code}


def _sign_out_others(db: Session, acc: SeekerAccount, keep: SeekerSession) -> None:
    """Signs every other browser out of the account after its password changes, so someone who knew the old
    password (or a forgotten shared device) loses access. Only the sign-in link is dropped: no session row and
    no data is deleted. The account's home session keeps everything filed under it; if its browser was still
    signed in, it now answers 401 like after a normal sign-out (see deps.signed_out_home) and starts afresh."""
    db.execute(update(SeekerSession).where(SeekerSession.account_id == acc.id, SeekerSession.id != keep.id)
               .values(account_id=None))


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
    age_band: str | None = None                               # one of AGE_BANDS (it can be changed, not removed)
    gender: str | None = None                                 # m | f (it can be changed, not removed)

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str | None) -> str | None:
        return _clean_email(v)

    @field_validator("country")
    @classmethod
    def valid_country(cls, v: str | None) -> str | None:
        return _country(v)

    @field_validator("age_band")
    @classmethod
    def valid_age_band(cls, v: str | None) -> str | None:
        return _check(v, AGE_BANDS, "age_band")

    @field_validator("gender")
    @classmethod
    def valid_gender(cls, v: str | None) -> str | None:
        return _check(v, GENDERS, "gender")


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
    if body.age_band is not None:
        acc.age_band = body.age_band
    if body.gender is not None:
        acc.gender = body.gender
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
    _sign_out_others(db, acc, device)
    _join(db, device, acc)
    db.commit()
    return {"account": account_view(acc)}


class PasswordIn(BaseModel):
    password: str = Field(max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


@router.post("/account/password")
def change_password(body: PasswordIn, device: SeekerSession = Depends(seeker_device), db: Session = Depends(get_db)):
    """Changes the password and signs the account out on every other browser (this one stays signed in)."""
    acc = _signed_in(device, db)
    if not verify_password(body.password, acc.password_hash):
        raise HTTPException(403, "wrong password")
    acc.password_hash = hash_password(body.new_password)
    _sign_out_others(db, acc, device)
    db.commit()
    return {"ok": True}


class ConfirmPasswordIn(BaseModel):
    password: str = Field(max_length=200)


@router.post("/account/recovery-code")
def new_recovery_code(body: ConfirmPasswordIn, device: SeekerSession = Depends(seeker_device),
                      db: Session = Depends(get_db)):
    """Issues a new one-time recovery code and replaces the stored hash, so any earlier code stops working.

    The web app no longer shows a code at sign-up, and email needs SMTP, so this is how a seeker makes sure a
    forgotten password can still be reset. Only the hash is kept: the code is shown once, in this answer."""
    acc = _signed_in(device, db)
    key = _key(acc.username)
    if _too_many(key):
        raise HTTPException(429, "too many attempts")
    if not verify_password(body.password, acc.password_hash):
        _failed(key)
        raise HTTPException(403, "wrong password")
    code = _recovery_code()
    acc.recovery_hash = hash_password(code)
    db.commit()
    return {"recovery_code": code}


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
    key = "daai:" + _key(body.username)
    if _too_many(key):
        raise HTTPException(429, "too many attempts")
    user = db.query(Daai).filter(Daai.username == body.username.strip().lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        _failed(key)
        raise HTTPException(401, "wrong username or password")
    if not user.active:
        raise HTTPException(403, "account disabled")
    _failures.pop(key, None)
    return {"token": _daai_token(user), "me": profile(user)}


def profile(user: Daai) -> dict:
    return {"id": user.id, "username": user.username, "name": user.display_name, "name_en": user.display_name_en,
            "gender": user.gender, "languages": user.languages or [], "role": user.role,
            "available": user.available, "bio": user.bio, "bio_en": user.bio_en, "country": user.country or "",
            "city": user.city or "", "active": user.active is not False, "is_demo": user.is_demo}


@router.get("/daai/me")
def me(user: Daai = Depends(daai), authorization: str = Header(default="")):
    """The da'i's profile. Once the token is past half its life the answer also carries a fresh `token`, so a
    console that keeps checking in (it polls this every 30 s) never hits the hard 12-hour end mid-shift."""
    out = profile(user)
    body = unsign(authorization.removeprefix("Bearer ").strip()) or {}
    if needs_refresh(body):
        out["token"] = _daai_token(user)
    return out


def _daai_token(user: Daai) -> str:
    return sign({"kind": "daai", "id": user.id, "v": user.token_version or 0})


class DaaiPasswordIn(BaseModel):
    password: str = Field(max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


@router.post("/daai/password")
def daai_password(body: DaaiPasswordIn, user: Daai = Depends(daai), db: Session = Depends(get_db)):
    """A da'i changes their own password. Every other session is signed out (token_version goes up) and this
    one gets a fresh token. The shared sample accounts can't be changed here, or one visitor could lock the
    judges out of the reviewer and sample da'i logins."""
    if user.is_demo:
        raise HTTPException(403, "demo account")
    key = "daai:" + user.username
    if _too_many(key):
        raise HTTPException(429, "too many attempts")
    if not verify_password(body.password, user.password_hash):
        _failed(key)
        raise HTTPException(403, "wrong password")
    user.password_hash = hash_password(body.new_password)
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    return {"token": _daai_token(user), "me": profile(user)}


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
    gender: str | None = None                                  # m | f: seekers may ask for a da'i of their gender
    country: str | None = Field(default=None, max_length=2)    # ISO code, "" for none
    city: str | None = Field(default=None, max_length=64)

    @field_validator("gender")
    @classmethod
    def known_gender(cls, v: str | None) -> str | None:
        return _check(v, ("m", "f"), "gender")   # a da'i's sex is required: seekers can ask for it

    @field_validator("country")
    @classmethod
    def country_code(cls, v: str | None) -> str | None:
        return _country(v)

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
                    "bio": "bio", "bio_en": "bio_en", "gender": "gender", "country": "country", "city": "city"}


@router.post("/daai/profile")
def update_me(body: ProfileIn, user: Daai = Depends(daai), db: Session = Depends(get_db)):
    """Lets a da'i keep their name, languages, gender, place and bio current, because seekers are matched on them."""
    _apply_profile(user, body)
    db.commit()
    return profile(user)


def _apply_profile(user: Daai, body: ProfileIn) -> None:
    moved = body.country is not None and body.city is None and body.country != (user.country or "")
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        setattr(user, _PROFILE_COLUMNS[key], value.strip() if isinstance(value, str) else value)
    if moved:
        user.city = ""   # a city from the old country no longer applies


# ---------------------------------------------------------------------------
# Da'i accounts, managed by the reviewer (role admin): add, edit, disable and reset passwords.
# ---------------------------------------------------------------------------

DAAI_USERNAME = re.compile(r"^[a-z0-9_.]{3,32}$")


class NewDaaiIn(ProfileIn):
    username: str = Field(max_length=32)
    password: str = Field(min_length=8, max_length=200)
    name: str = Field(max_length=120)
    languages: list[str] = Field(default_factory=lambda: ["ar"])
    role: str = "daai"

    @field_validator("username")
    @classmethod
    def valid_username(cls, v: str) -> str:
        v = v.strip().lower()
        if not DAAI_USERNAME.match(v):
            raise ValueError("username: 3-32 lower-case letters, digits, _ or .")
        return v

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str) -> str:
        if v not in ("daai", "admin"):
            raise ValueError("role must be daai or admin")
        return v


class EditDaaiIn(ProfileIn):
    active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)   # a new password for the da'i


@router.get("/daai/admin/daais")
def list_daais(_: Daai = Depends(admin), db: Session = Depends(get_db)):
    return [profile(d) for d in db.scalars(select(Daai).order_by(Daai.id)).all()]


@router.post("/daai/admin/daais")
def add_daai(body: NewDaaiIn, _: Daai = Depends(admin), db: Session = Depends(get_db)):
    if db.scalars(select(Daai).where(Daai.username == body.username)).first():
        raise HTTPException(409, "username taken")
    user = create_daai(db, body.username, body.password, display_name=body.name.strip(), role=body.role,
                       languages=body.languages)
    _apply_profile(user, ProfileIn(**body.model_dump(exclude={"username", "password", "role"}, exclude_unset=True)))
    db.commit()
    return profile(user)


@router.post("/daai/admin/daais/{did}")
def edit_daai(did: int, body: EditDaaiIn, me: Daai = Depends(admin), db: Session = Depends(get_db)):
    user = db.get(Daai, did)
    if not user:
        raise HTTPException(404, "not found")
    if body.active is False and user.id == me.id:
        raise HTTPException(400, "you can't disable your own account")
    _apply_profile(user, ProfileIn(**body.model_dump(exclude={"active", "password"}, exclude_unset=True)))
    if body.active is not None:
        user.active = body.active
        if not body.active:
            user.available = False
    if body.password:
        user.password_hash = hash_password(body.password)
        user.token_version = (user.token_version or 0) + 1   # signs the da'i out everywhere
    db.commit()
    return profile(user)


def create_daai(db: Session, username: str, password: str, **fields) -> Daai:
    user = Daai(username=username.lower(), password_hash=hash_password(password), **fields)
    db.add(user)
    db.flush()
    return user
