"""Calls API: availability, call requests, the da'i's queue and the referral experiment. Owner: Eman.

Calls do not depend on the model at all: a seeker can call without asking the
assistant first, and calls keep working when Claude is unavailable. Audio is
peer-to-peer WebRTC (or relayed through TURN when CALL_RELAY_ONLY is set); the
server only relays signalling and the in-call text chat (signalling.py).

Contract used by frontend/src/features/calls (see docs/API.md).
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.db import Daai, SeekerSession, Setting, get_db, iso, utcnow
from ...core.deps import admin, daai, seeker
from ..rag.public import source_card
from .models import CallMessage, CallRequest, Referral

router = APIRouter(prefix="/api")

ONLINE_WINDOW = timedelta(seconds=90)
LANGS = {"ar", "en", "fr", "ur", "id", "tr", "es", "de", "bn", "ru", "zh", "sw", "ha", "so", "fa"}


def online_daais(db: Session):
    since = utcnow() - ONLINE_WINDOW
    return db.scalars(select(Daai).where(Daai.available.is_(True), Daai.last_seen >= since,
                                         Daai.role == "daai")).all()


@router.get("/availability")
def availability(db: Session = Depends(get_db)):
    counts: dict[str, dict[str, int]] = {}
    for d in online_daais(db):
        for lang in d.languages or []:
            c = counts.setdefault(lang, {"total": 0, "m": 0, "f": 0})
            c["total"] += 1
            c[d.gender] = c.get(d.gender, 0) + 1
    return {"languages": counts}


@router.get("/rtc-config")
def rtc_config():
    servers = [{"urls": settings.stun_urls}] if settings.stun_urls else []
    if settings.turn_url:
        servers.append({"urls": [settings.turn_url], "username": settings.turn_username,
                        "credential": settings.turn_credential})
    return {"iceServers": servers, "iceTransportPolicy": "relay" if settings.call_relay_only and settings.turn_url else "all"}


class CallIn(BaseModel):
    lang: str
    gender_pref: str = ""
    referral_id: int | None = None


def _expire(db: Session, call: CallRequest) -> None:
    if call.status == "waiting" and utcnow() - call.created_at > timedelta(seconds=settings.call_wait_seconds):
        call.status = "expired"
        db.commit()


@router.post("/calls")
def request_call(body: CallIn, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    if body.lang not in LANGS:
        raise HTTPException(400, "unsupported language")
    if body.gender_pref not in ("", "m", "f"):
        raise HTTPException(400, "bad gender preference")
    if body.referral_id:
        ref = db.get(Referral, body.referral_id)
        if not ref or ref.session_id != me.id:
            raise HTTPException(404, "referral not found")
    # One open request per seeker.
    for old in db.scalars(select(CallRequest).where(CallRequest.session_id == me.id,
                                                    CallRequest.status.in_(("waiting",)))).all():
        old.status = "cancelled"
    call = CallRequest(session_id=me.id, lang=body.lang, gender_pref=body.gender_pref, referral_id=body.referral_id)
    db.add(call)
    db.commit()
    return {"id": call.id, "status": call.status}


def _call_view(call: CallRequest, db: Session) -> dict:
    d = db.get(Daai, call.daai_id) if call.daai_id else None
    waiting_ahead = 0
    if call.status == "waiting":
        waiting_ahead = len(db.scalars(select(CallRequest.id).where(
            CallRequest.status == "waiting", CallRequest.lang == call.lang, CallRequest.id < call.id)).all())
    return {"id": call.id, "status": call.status, "lang": call.lang,
            "daai": {"name": d.display_name, "name_en": d.display_name_en, "gender": d.gender} if d else None,
            "queue_position": waiting_ahead, "created_at": iso(call.created_at)}


@router.get("/calls/{cid}")
def call_status(cid: int, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    call = db.get(CallRequest, cid)
    if not call or call.session_id != me.id:
        raise HTTPException(404, "not found")
    _expire(db, call)
    return _call_view(call, db)


@router.post("/calls/{cid}/cancel")
def cancel_call(cid: int, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    call = db.get(CallRequest, cid)
    if not call or call.session_id != me.id:
        raise HTTPException(404, "not found")
    if call.status == "waiting":
        call.status = "cancelled"
    elif call.status == "accepted":
        call.status, call.ended_at = "ended", utcnow()
    db.commit()
    return _call_view(call, db)


class RateIn(BaseModel):
    rating: int


@router.post("/calls/{cid}/rate")
def rate_call(cid: int, body: RateIn, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    call = db.get(CallRequest, cid)
    if not call or call.session_id != me.id:
        raise HTTPException(404, "not found")
    call.seeker_rating = max(1, min(5, body.rating))
    db.commit()
    return {"ok": True}


@router.get("/calls/{cid}/messages")
def call_messages(cid: int, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    call = db.get(CallRequest, cid)
    if not call or call.session_id != me.id:
        raise HTTPException(404, "not found")
    msgs = db.scalars(select(CallMessage).where(CallMessage.call_id == cid).order_by(CallMessage.id)).all()
    return [{"id": m.id, "sender": m.sender, "text": m.text, "at": iso(m.created_at)} for m in msgs]


# ---------------------------------------------------------------------------
# Da'i side
# ---------------------------------------------------------------------------

@router.get("/daai/requests")
def daai_requests(me: Daai = Depends(daai), db: Session = Depends(get_db)):
    waiting = db.scalars(select(CallRequest).where(CallRequest.status == "waiting")
                         .order_by(CallRequest.id)).all()
    out = []
    for c in waiting:
        _expire(db, c)
        if c.status != "waiting" or c.lang not in (me.languages or []):
            continue
        if c.gender_pref and c.gender_pref != me.gender:
            continue
        ref = db.get(Referral, c.referral_id) if c.referral_id else None
        out.append({"id": c.id, "lang": c.lang, "waiting_seconds": int((utcnow() - c.created_at).total_seconds()),
                    "has_card": bool(ref and ref.consented and ref.final)})
    mine = db.scalars(select(CallRequest).where(CallRequest.daai_id == me.id, CallRequest.status == "accepted")).all()
    return {"waiting": out, "active": [{"id": c.id, "lang": c.lang} for c in mine]}


@router.post("/daai/requests/{cid}/accept")
def accept_request(cid: int, me: Daai = Depends(daai), db: Session = Depends(get_db)):
    call = db.get(CallRequest, cid)
    if not call or call.lang not in (me.languages or []) or (call.gender_pref and call.gender_pref != me.gender):
        raise HTTPException(404, "not found")
    # Atomic: only one da'i can take a waiting request.
    res = db.execute(update(CallRequest).where(CallRequest.id == cid, CallRequest.status == "waiting")
                     .values(status="accepted", daai_id=me.id, accepted_at=utcnow()))
    db.commit()
    if res.rowcount != 1:
        raise HTTPException(409, "already taken or no longer waiting")
    return daai_call(cid, me, db)


@router.get("/daai/calls/{cid}")
def daai_call(cid: int, me: Daai = Depends(daai), db: Session = Depends(get_db)):
    call = db.get(CallRequest, cid)
    if not call or call.daai_id != me.id:
        raise HTTPException(404, "not found")
    ref = db.get(Referral, call.referral_id) if call.referral_id else None
    card = ref.final if ref and ref.consented else None
    if card and not call.card_opened_at:
        call.card_opened_at = utcnow()
        db.commit()
    sources = {}
    for item in (card or {}).get("explained", []):
        for sid in item.get("sources", []):
            c = source_card(sid, "ar" if call.lang == "ar" else "en")
            if c:
                sources[sid] = c
    return {"id": call.id, "status": call.status, "lang": call.lang, "card": card, "card_sources": sources,
            "referral_mode": ref.mode if ref else "direct",
            "accepted_at": iso(call.accepted_at),
            "understood": bool(call.understood_at)}


@router.post("/daai/calls/{cid}/understood")
def mark_understood(cid: int, me: Daai = Depends(daai), db: Session = Depends(get_db)):
    call = db.get(CallRequest, cid)
    if not call or call.daai_id != me.id:
        raise HTTPException(404, "not found")
    if not call.understood_at:
        call.understood_at = utcnow()
        db.commit()
    return {"ok": True}


class DaaiFeedback(BaseModel):
    reexplain_needed: bool | None = None
    card_accurate: bool | None = None
    note: str = ""


@router.post("/daai/calls/{cid}/end")
def daai_end_call(cid: int, body: DaaiFeedback, me: Daai = Depends(daai), db: Session = Depends(get_db)):
    call = db.get(CallRequest, cid)
    if not call or call.daai_id != me.id:
        raise HTTPException(404, "not found")
    if call.status == "accepted":
        call.status, call.ended_at = "ended", utcnow()
    call.reexplain_needed = body.reexplain_needed
    call.card_accurate = body.card_accurate
    call.daai_note = body.note[:500]
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Referral experiment (reviewer/admin)
# ---------------------------------------------------------------------------

class ExperimentIn(BaseModel):
    enabled: bool


@router.post("/daai/experiment")
def set_experiment(body: ExperimentIn, _: Daai = Depends(admin), db: Session = Depends(get_db)):
    row = db.get(Setting, "referral_experiment")
    if row:
        row.value = {**row.value, "enabled": body.enabled}
    else:
        db.add(Setting(key="referral_experiment", value={"enabled": body.enabled, "counter": 0}))
    db.commit()
    return {"enabled": body.enabled}


@router.get("/daai/experiment")
def experiment_results(_: Daai = Depends(daai), db: Session = Depends(get_db)):
    """Per arm: calls, share needing re-explanation, card accuracy, seconds until the da'i understood."""
    row = db.get(Setting, "referral_experiment")
    rows = db.execute(select(Referral.mode, CallRequest).join(CallRequest, CallRequest.referral_id == Referral.id)
                      .where(CallRequest.status == "ended")).all()
    direct = db.scalars(select(CallRequest).where(CallRequest.referral_id.is_(None),
                                                  CallRequest.status == "ended")).all()
    arms: dict[str, list[CallRequest]] = {}
    for mode, call in rows:
        arms.setdefault(mode, []).append(call)
    arms.setdefault("direct", []).extend(direct)

    def summary(calls: list[CallRequest]) -> dict:
        rated = [c for c in calls if c.reexplain_needed is not None]
        acc = [c for c in calls if c.card_accurate is not None]
        times = sorted((c.understood_at - c.accepted_at).total_seconds()
                       for c in calls if c.understood_at and c.accepted_at)
        return {"calls": len(calls),
                "no_reexplain_rate": round(sum(1 for c in rated if not c.reexplain_needed) / len(rated), 2) if rated else None,
                "card_accurate_rate": round(sum(1 for c in acc if c.card_accurate) / len(acc), 2) if acc else None,
                "median_seconds_to_understand": times[len(times) // 2] if times else None}

    return {"enabled": bool(row and row.value.get("enabled")),
            "arms": {k: summary(v) for k, v in arms.items()},
            "waiting_now": db.scalar(select(func.count()).select_from(CallRequest).where(CallRequest.status == "waiting"))}
