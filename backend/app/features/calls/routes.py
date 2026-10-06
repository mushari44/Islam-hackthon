"""Calls API: availability, call requests, the da'i's queue and the referral experiment. Owner: Eman.

Calls do not depend on the model at all: a seeker can call without asking the
assistant first, and calls keep working when Claude is unavailable. Audio is
peer-to-peer WebRTC (or relayed through TURN when CALL_RELAY_ONLY is set); the
server only relays signalling and the in-call text chat (signalling.py).

Contract used by frontend/src/features/calls (see docs/API.md).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.db import Setting, get_db, iso, utcnow
from ..auth.public import Daai, SeekerSession, admin, daai, is_account, seeker
from ..community.public import mark_new_muslim, new_muslim_calls, unmark_new_muslim
from ..rag.public import shared_conversation, source_card
from . import booking
from .models import CallMessage, CallRequest, Referral
from .signalling import end_abandoned_calls

router = APIRouter(prefix="/api")
router.include_router(booking.router)   # booked calls (weekly hours, slots, bookings) live in booking.py

ONLINE_WINDOW = timedelta(seconds=90)
# The seeker's waiting screen polls its request every ~2 s. Closing the tab stops that: after SEEKER_AWAY the
# request is hidden from the da'is (and can't be accepted), after SEEKER_GONE it expires. A reload within that
# time resumes it, because the page remembers the request and polls it again.
SEEKER_AWAY = timedelta(seconds=70)   # > 60 s too, so a waiting seeker in a background tab stays listed
SEEKER_GONE = timedelta(seconds=90)   # > 60 s: Chrome slows a long-hidden tab's timers to one a minute
LANGS = {"ar", "en"}   # the languages we support for now; add more when da'is and content cover them


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


def _directory_entry(d: Daai, lang: str, online: set[int], bookable: bool = False) -> dict:
    return {**d.public(lang), "bio": d.bio if lang == "ar" else (d.bio_en or d.bio), "online": d.id in online,
            "bookable": bookable}


def _callable(d: Daai | None) -> bool:
    return bool(d and d.role == "daai" and d.active is not False)


@router.get("/daais")
def daai_directory(lang: str = "", ui: str = "ar", db: Session = Depends(get_db)):
    """Da'is a seeker can ask for by name, online first. `lang` keeps only those who speak it."""
    online = {d.id for d in online_daais(db)}
    ui = "ar" if ui == "ar" else "en"
    people = [d for d in db.scalars(select(Daai).order_by(Daai.id)).all()
              if _callable(d) and (not lang or lang in (d.languages or []))]
    people.sort(key=lambda d: d.id not in online)
    return [_directory_entry(d, ui, online, booking.bookable(db, d)) for d in people]


@router.get("/rtc-config")
def rtc_config():
    servers = [{"urls": settings.stun_urls}] if settings.stun_urls else []
    if settings.turn_url:
        # TURN_URL may list several addresses separated by commas (e.g. port 80, 443 and turns: over TLS).
        urls = [u.strip() for u in settings.turn_url.split(",") if u.strip()]
        servers.append({"urls": urls, "username": settings.turn_username, "credential": settings.turn_credential})
    return {"iceServers": servers, "iceTransportPolicy": "relay" if settings.call_relay_only and settings.turn_url else "all"}


class CallIn(BaseModel):
    lang: str
    gender_pref: str = ""
    referral_id: int | None = None
    daai_id: int | None = None   # ask for this da'i only


def _unseen(call: CallRequest) -> timedelta:
    """How long the seeker's waiting screen has been silent (rows from before last_seen_at count from creation)."""
    return utcnow() - (call.last_seen_at or call.created_at)


def _expire(db: Session, call: CallRequest) -> None:
    if call.status == "waiting" and (utcnow() - call.created_at > timedelta(seconds=settings.call_wait_seconds)
                                     or _unseen(call) > SEEKER_GONE):
        call.status = "expired"
        db.commit()


def _present_waiting():
    """SQL filter for waiting requests whose seeker is still on the waiting screen."""
    since = utcnow() - SEEKER_AWAY
    return (CallRequest.status == "waiting") & (func.coalesce(CallRequest.last_seen_at, CallRequest.created_at) >= since)


@router.post("/calls")
def request_call(body: CallIn, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    # A live call needs a seeker account, as booking does: the da'i talks to someone who can be reached again,
    # and the call log, rating and "call the same da'i again" follow the seeker to any device.
    if not is_account(db, me.id):
        raise HTTPException(403, "sign in to call")
    if body.lang not in LANGS:
        raise HTTPException(400, "unsupported language")
    if body.gender_pref not in ("", "m", "f"):
        raise HTTPException(400, "bad gender preference")
    if body.referral_id:
        ref = db.get(Referral, body.referral_id)
        if not ref or ref.session_id != me.id:
            raise HTTPException(404, "referral not found")
    if body.daai_id is not None:
        wanted = db.get(Daai, body.daai_id)
        if not _callable(wanted):
            raise HTTPException(404, "da'i not found")
        if body.lang not in (wanted.languages or []):
            raise HTTPException(400, "this da'i doesn't speak that language")
        if body.gender_pref and body.gender_pref != wanted.gender:
            raise HTTPException(400, "bad gender preference")
    # One open request per seeker.
    for old in db.scalars(select(CallRequest).where(CallRequest.session_id == me.id,
                                                    CallRequest.status.in_(("waiting",)))).all():
        old.status = "cancelled"
    call = CallRequest(session_id=me.id, lang=body.lang, gender_pref=body.gender_pref, referral_id=body.referral_id,
                       daai_pref=body.daai_id)
    db.add(call)
    db.commit()
    return {"id": call.id, "status": call.status}


def _call_view(call: CallRequest, db: Session) -> dict:
    d = db.get(Daai, call.daai_id) if call.daai_id else None
    waiting_ahead = 0
    if call.status == "waiting":
        # A request for a named da'i only queues behind requests for the same da'i, and the general queue
        # doesn't count requests that only one other da'i can take.
        same_queue = (CallRequest.daai_pref == call.daai_pref) if call.daai_pref else CallRequest.daai_pref.is_(None)
        waiting_ahead = len(db.scalars(select(CallRequest.id).where(
            _present_waiting(), CallRequest.lang == call.lang, CallRequest.id < call.id, same_queue)).all())
    return {"id": call.id, "status": call.status, "lang": call.lang,
            "daai": {"id": d.id, "name": d.display_name, "name_en": d.display_name_en, "gender": d.gender} if d else None,
            "daai_pref": call.daai_pref, "queue_position": waiting_ahead, "created_at": iso(call.created_at)}


@router.get("/calls/conversations")
def calls_by_conversation(me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    """Which da'i this seeker talked to about each Ask conversation (newest call first), so the chat list
    can show it and offer to call the same da'i again. Declared before /calls/{cid}."""
    rows = db.execute(select(Referral.conversation_id, CallRequest)
                      .join(CallRequest, CallRequest.referral_id == Referral.id)
                      .where(CallRequest.session_id == me.id, Referral.conversation_id.is_not(None),
                             CallRequest.daai_id.is_not(None), CallRequest.accepted_at.is_not(None))
                      .order_by(CallRequest.accepted_at.desc())).all()
    out = []
    for conv_id, call in rows:
        d = db.get(Daai, call.daai_id)
        if d:
            out.append({"conversation_id": conv_id, "call_id": call.id, "at": iso(call.accepted_at), "lang": call.lang,
                        "daai": {"id": d.id, "name": d.display_name, "name_en": d.display_name_en,
                                 "callable": _callable(d)}})
    return out


@router.get("/calls/{cid}")
def call_status(cid: int, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    call = db.get(CallRequest, cid)
    if not call or call.session_id != me.id:
        raise HTTPException(404, "not found")
    _expire(db, call)
    if call.status == "waiting":
        call.last_seen_at = utcnow()   # the waiting screen's poll is the heartbeat that keeps it in the queue
        db.commit()
    return _call_view(call, db)


@router.get("/calls")
def my_calls(me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    """The da'is this seeker has talked to (newest first, one entry each), so they can call the same one again."""
    calls = db.scalars(select(CallRequest).where(CallRequest.session_id == me.id, CallRequest.daai_id.is_not(None),
                                                 CallRequest.accepted_at.is_not(None))
                       .order_by(CallRequest.accepted_at.desc())).all()
    online = {d.id for d in online_daais(db)}
    out, seen = [], set()
    for c in calls:
        d = db.get(Daai, c.daai_id)
        if c.daai_id in seen or not _callable(d):
            continue
        seen.add(c.daai_id)
        out.append({"daai": {"id": d.id, "name": d.display_name, "name_en": d.display_name_en, "gender": d.gender,
                             "languages": d.languages or [], "online": d.id in online},
                    "last_call_at": iso(c.accepted_at), "lang": c.lang})
    return out


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
        if c.status != "waiting" or c.lang not in (me.languages or []) or _unseen(c) > SEEKER_AWAY:
            continue
        if c.gender_pref and c.gender_pref != me.gender:
            continue
        if c.daai_pref and c.daai_pref != me.id:
            continue
        ref = db.get(Referral, c.referral_id) if c.referral_id else None
        out.append({"id": c.id, "lang": c.lang, "waiting_seconds": int((utcnow() - c.created_at).total_seconds()),
                    "has_card": bool(ref and ref.consented and ref.final), "has_chat": bool(ref and ref.share_chat),
                    "for_you": c.daai_pref == me.id})
    out.sort(key=lambda r: not r["for_you"])   # requests made for this da'i by name come first
    end_abandoned_calls(db, me.id)
    booked = booking.booked_soon(db, me)
    if booked:
        # A booked call starts soon: keep the time free by holding back new requests from the general queue.
        out = [r for r in out if r["for_you"]]
    mine = db.scalars(select(CallRequest).where(CallRequest.daai_id == me.id, CallRequest.status == "accepted")).all()
    return {"waiting": out, "active": [{"id": c.id, "lang": c.lang} for c in mine], "booked": booked,
            "bookings_today": booking.bookings_today(db, me)}


@router.post("/daai/requests/{cid}/accept")
def accept_request(cid: int, me: Daai = Depends(daai), db: Session = Depends(get_db)):
    call = db.get(CallRequest, cid)
    if not call or call.lang not in (me.languages or []) or (call.gender_pref and call.gender_pref != me.gender) \
            or (call.daai_pref and call.daai_pref != me.id):
        raise HTTPException(404, "not found")
    _expire(db, call)
    if call.status in ("waiting", "expired") and _unseen(call) > SEEKER_AWAY:
        raise HTTPException(409, "seeker left")
    # Atomic: only one da'i can take a waiting request, and only while its seeker is still there.
    res = db.execute(update(CallRequest).where(CallRequest.id == cid, _present_waiting())
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
    # Only with the seeker's explicit OK, and only what the chat held when they agreed; gone if they deleted it.
    chat = shared_conversation(db, ref.session_id, ref.conversation_id, ref.chat_upto) \
        if ref and ref.share_chat and ref.conversation_id and ref.chat_upto else []
    return {"id": call.id, "status": call.status, "lang": call.lang, "card": card, "card_sources": sources,
            "chat": chat or None, "referral_mode": ref.mode if ref else "direct",
            "accepted_at": iso(call.accepted_at),
            "understood": bool(call.understood_at),
            "new_muslim": new_muslim_calls(db, [call.id]).get(call.id),
            "booking": booking.booking_for_call(db, call.id)}


def _own_answered_call(db: Session, cid: int, me: Daai) -> CallRequest:
    call = db.get(CallRequest, cid)
    if not call or call.daai_id != me.id or call.status not in ("accepted", "ended"):
        raise HTTPException(404, "not found")
    return call


@router.post("/daai/calls/{cid}/new-muslim")
def confirm_new_muslim(cid: int, me: Daai = Depends(daai), db: Session = Depends(get_db)):
    """The da'i confirms the seeker embraced Islam in this call (during it or afterwards). Community then asks
    the seeker whether to share the news with their groups; nothing is announced without their yes."""
    call = _own_answered_call(db, cid, me)
    return {"new_muslim": mark_new_muslim(db, call.session_id, call.id, me.id)}


@router.delete("/daai/calls/{cid}/new-muslim")
def undo_new_muslim(cid: int, me: Daai = Depends(daai), db: Session = Depends(get_db)):
    """Pressed by mistake: the da'i can take it back until the seeker has answered."""
    _own_answered_call(db, cid, me)
    if not unmark_new_muslim(db, cid, me.id):
        raise HTTPException(409, "the seeker already answered")
    return {"new_muslim": None}


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
# Monthly call log for the signed-in da'i: every call they answered, with dates.
# Numbers only: no audio is ever stored, and nothing that identifies the seeker leaves the server.
# ---------------------------------------------------------------------------

@router.get("/daai/calls")
def daai_call_log(month: str = "", me: Daai = Depends(daai), db: Session = Depends(get_db)):
    """The calls this da'i answered in one month (YYYY-MM, default this month), newest first, with dates."""
    now = utcnow()
    try:
        year, mon = (int(x) for x in month.split("-")) if month else (now.year, now.month)
        start = datetime(year, mon, 1)
    except ValueError:
        raise HTTPException(400, "month must be YYYY-MM")
    end = datetime(year + (mon == 12), mon % 12 + 1, 1)
    answered = select(CallRequest).where(CallRequest.daai_id == me.id, CallRequest.status == "ended",
                                         CallRequest.accepted_at.is_not(None))
    calls = db.scalars(answered.where(CallRequest.accepted_at >= start, CallRequest.accepted_at < end)
                       .order_by(CallRequest.accepted_at.desc())).all()
    months = sorted({c.accepted_at.strftime("%Y-%m") for c in db.scalars(answered).all()} | {now.strftime("%Y-%m")},
                    reverse=True)
    refs = {r.id: r for r in db.scalars(select(Referral).where(
        Referral.id.in_([c.referral_id for c in calls if c.referral_id])))} if calls else {}
    modes = {rid: r.mode for rid, r in refs.items()}
    converted = new_muslim_calls(db, [c.id for c in calls])

    def secs(a, b):
        return int((b - a).total_seconds()) if a and b else None

    items = [{"id": c.id, "lang": c.lang, "accepted_at": iso(c.accepted_at), "ended_at": iso(c.ended_at),
              "duration_seconds": secs(c.accepted_at, c.ended_at),
              "seconds_to_understand": secs(c.accepted_at, c.understood_at),
              "referral_mode": modes.get(c.referral_id, "direct") if c.referral_id else "direct",
              "reexplain_needed": c.reexplain_needed, "card_accurate": c.card_accurate,
              "seeker_rating": c.seeker_rating, "note": c.daai_note,
              "has_chat": bool(c.referral_id in refs and refs[c.referral_id].share_chat),
              "new_muslim": converted.get(c.id)} for c in calls]
    rated = [i for i in items if i["reexplain_needed"] is not None]
    stars = [i["seeker_rating"] for i in items if i["seeker_rating"]]
    return {"month": f"{year:04d}-{mon:02d}", "months": months, "calls": items,
            "summary": {"calls": len(items),
                        "minutes": round(sum(i["duration_seconds"] or 0 for i in items) / 60),
                        "no_reexplain": sum(1 for i in rated if not i["reexplain_needed"]),
                        "rated": len(rated),
                        "new_muslims": len(converted),
                        "avg_rating": round(sum(stars) / len(stars), 1) if stars else None}}

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
            "waiting_now": db.scalar(select(func.count()).select_from(CallRequest).where(_present_waiting()))}
