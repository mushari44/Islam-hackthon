"""Booked calls: a da'i's weekly hours, the free slots they give, and seekers' bookings. Owner: Eman.

A da'i sets weekly hours in their own time zone; the site cuts them into 30-minute slots. A signed-in
seeker books 30 or 60 minutes (60 needs the next half hour free too), up to 14 days ahead and at least
2 hours before. Bookings are confirmed straight away; either side can cancel before the start.

There is no email and no background job (Render's free plan sleeps), so every timed rule is worked out
when someone reads a booking (`_refresh`), the same way call requests expire:
- the Join button opens 5 minutes before the start;
- 10 minutes after the start, a booking nobody started is "missed" (by the da'i if the seeker was waiting);
- a booking whose call ended is "done".
The call itself is an ordinary CallRequest (same room, chat, card and rating), created when the da'i
presses Start. Contract in docs/API.md.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.db import get_db, iso, utcnow
from ..auth.public import Daai, SeekerSession, daai, is_account, optional_seeker, seeker
from .models import Booking, BookingBlock, CallRequest, DaaiSchedule, Referral

router = APIRouter()   # mounted under /api by routes.py

UNIT = 30                          # minutes in one slot; a booking is one or two of them
LENGTHS = (30, 60)
DAYS_AHEAD = 14
MIN_NOTICE = timedelta(hours=2)
MAX_UPCOMING = 3                   # upcoming bookings one seeker may hold at once
JOIN_EARLY = timedelta(minutes=5)
GRACE = timedelta(minutes=10)      # after this, a booking nobody started counts as missed
QUIET_BEFORE = timedelta(minutes=15)   # the da'i gets no new "call now" requests this close to a booked call
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")   # Python's weekday() order
HHMM = re.compile(r"^([01]\d|2[0-4]):(00|30)$")
ZONES = available_timezones()
DEFAULT_TZ = "Asia/Riyadh"
# Demo da'is come with hours so the booking flow can be tried straight away (all synthetic).
DEMO_WEEKLY = {d: [["10:00", "13:00"], ["17:00", "22:00"]] for d in DAYS}


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or DEFAULT_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _clock(s: str) -> time | None:
    """'18:30' -> 18:30; '24:00' (end of day) -> None, meaning midnight at the end of that day."""
    h, m = (int(x) for x in s.split(":"))
    return None if h == 24 else time(h, m)


def _local_to_utc(day: date, at: time | None, tz: ZoneInfo) -> datetime:
    local = datetime.combine(day + timedelta(days=1), time(0)) if at is None else datetime.combine(day, at)
    return local.replace(tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)


def get_schedule(db: Session, d: Daai) -> DaaiSchedule | None:
    row = db.get(DaaiSchedule, d.id)
    if row is None and d.is_demo and d.role == "daai":
        db.add(DaaiSchedule(daai_id=d.id, tz=DEFAULT_TZ, weekly=DEMO_WEEKLY, days_off=[], paused=False))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()   # a request running at the same time made it first
        row = db.get(DaaiSchedule, d.id)
    return row


def _callable(d: Daai | None) -> bool:
    return bool(d and d.role == "daai" and d.active is not False)


def bookable(db: Session, d: Daai) -> bool:
    row = get_schedule(db, d)
    return bool(_callable(d) and row and not row.paused and any(row.weekly.get(k) for k in DAYS))


def free_slots(db: Session, d: Daai, minutes: int = UNIT, now: datetime | None = None,
               ignore: int | None = None) -> list[datetime]:
    """Start times (UTC, naive) this da'i can still be booked at for `minutes`, soonest first. `ignore` is a
    booking being moved: its own time counts as free (so a seeker can extend 30 minutes to 60 in place)."""
    row = get_schedule(db, d)
    if not row or row.paused or not _callable(d):
        return []
    now = now or utcnow()
    earliest, latest = now + MIN_NOTICE, now + timedelta(days=DAYS_AHEAD)
    q = select(BookingBlock.starts_at).where(BookingBlock.daai_id == d.id, BookingBlock.starts_at >= now - timedelta(hours=1))
    if ignore is not None:
        q = q.where(BookingBlock.booking_id != ignore)
    taken = set(db.scalars(q).all())
    tz = _zone(row.tz)
    today = now.replace(tzinfo=timezone.utc).astimezone(tz).date()
    off = set(row.days_off or [])
    need = minutes // UNIT
    out = []
    for i in range(DAYS_AHEAD + 1):
        day = today + timedelta(days=i)
        if day.isoformat() in off:
            continue
        for a, b in row.weekly.get(DAYS[day.weekday()], []):
            start, end = _local_to_utc(day, _clock(a), tz), _local_to_utc(day, _clock(b), tz)
            at = start
            while at + timedelta(minutes=minutes) <= end:
                if earliest <= at <= latest and all(at + timedelta(minutes=UNIT * k) not in taken for k in range(need)):
                    out.append(at)
                at += timedelta(minutes=UNIT)
    return sorted(set(out))


def _parse_utc(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, "bad time")
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


# ---------------------------------------------------------------------------
# Keeping a booking's state current (there are no background jobs)
# ---------------------------------------------------------------------------

def _free(db: Session, b: Booking) -> None:
    db.execute(delete(BookingBlock).where(BookingBlock.booking_id == b.id))


def _refresh(db: Session, b: Booking, now: datetime | None = None) -> Booking:
    if b.status != "booked":
        return b
    now = now or utcnow()
    d = db.get(Daai, b.daai_id)
    call = db.get(CallRequest, b.call_id) if b.call_id else None
    if not _callable(d) and not call:
        b.status, b.cancelled_by = "cancelled", "system"
        _free(db, b)
    elif call and call.status in ("ended", "cancelled", "expired"):
        # The da'i started and ended it, but the seeker never came to the waiting room: a no-show, not a call.
        b.status, b.missed_by = ("done", "") if b.seeker_ready_at else ("missed", "seeker")
    elif now > b.starts_at + GRACE:
        if not call:
            # Nobody started it: the da'i missed it (the seeker was waiting), or neither side came.
            b.status, b.missed_by = "missed", ("daai" if b.seeker_ready_at else "both")
        elif call.status == "accepted" and not b.seeker_ready_at:
            # The da'i started and waited; the seeker never came. Close the empty room.
            b.status, b.missed_by = "missed", "seeker"
            call.status, call.ended_at = "ended", now
    db.commit()
    return b


def _times(b: Booking, now: datetime) -> dict:
    end = b.starts_at + timedelta(minutes=b.minutes)
    live = b.status == "booked"
    return {"starts_at": iso(b.starts_at), "ends_at": iso(end), "minutes": b.minutes,
            "join_opens_at": iso(b.starts_at - JOIN_EARLY),
            "can_join": live and b.starts_at - JOIN_EARLY <= now <= max(end, b.starts_at + GRACE),
            "can_cancel": live and now < b.starts_at and not b.call_id}


def _daai_brief(d: Daai | None) -> dict | None:
    return {"id": d.id, "name": d.display_name, "name_en": d.display_name_en, "gender": d.gender} if d else None


def seeker_view(db: Session, b: Booking, now: datetime | None = None) -> dict:
    now = now or utcnow()
    call = db.get(CallRequest, b.call_id) if b.call_id else None
    return {"id": b.id, "status": b.status, "lang": b.lang, "note": b.note, "daai": _daai_brief(db.get(Daai, b.daai_id)),
            "cancelled_by": b.cancelled_by, "cancel_note": b.cancel_note, "missed_by": b.missed_by,
            "ready": bool(b.seeker_ready_at), "call_id": b.call_id if call and call.status == "accepted" else None,
            "rescheduled_to": b.rescheduled_to,
            "has_card": bool(b.referral_id), "created_at": iso(b.created_at), **_times(b, now)}


def daai_view(db: Session, b: Booking, now: datetime | None = None) -> dict:
    """What the da'i sees: never who the seeker is, only the time, language, topic and whether a card is shared."""
    now = now or utcnow()
    ref = db.get(Referral, b.referral_id) if b.referral_id else None
    t = _times(b, now)
    end = b.starts_at + timedelta(minutes=b.minutes)
    return {"id": b.id, "status": b.status, "lang": b.lang, "note": b.note, "missed_by": b.missed_by,
            "cancelled_by": b.cancelled_by, "rescheduled": bool(b.rescheduled_to), "seeker_waiting": bool(b.seeker_ready_at) and b.status == "booked",
            "has_card": bool(ref and ref.consented and ref.final), "has_chat": bool(ref and ref.share_chat),
            "call_id": b.call_id, "can_start": b.status == "booked" and b.starts_at - JOIN_EARLY <= now <= max(end, b.starts_at + GRACE),
            **{k: t[k] for k in ("starts_at", "ends_at", "minutes", "can_cancel")}}


# ---------------------------------------------------------------------------
# Da'i: weekly hours, days off, pause, their bookings, start and cancel
# ---------------------------------------------------------------------------

class ScheduleIn(BaseModel):
    tz: str = DEFAULT_TZ
    weekly: dict[str, list[list[str]]] = Field(default_factory=dict)
    days_off: list[str] = Field(default_factory=list, max_length=120)
    paused: bool = False


def _schedule_out(row: DaaiSchedule | None) -> dict:
    if not row:
        return {"tz": "", "weekly": {}, "days_off": [], "paused": False, "slot_minutes": UNIT, "set": False}
    return {"tz": row.tz, "weekly": {k: row.weekly.get(k, []) for k in DAYS}, "days_off": sorted(row.days_off or []),
            "paused": row.paused, "slot_minutes": UNIT, "set": True}


@router.get("/daai/schedule")
def my_schedule(me: Daai = Depends(daai), db: Session = Depends(get_db)):
    return _schedule_out(get_schedule(db, me))


@router.post("/daai/schedule")
def save_schedule(body: ScheduleIn, me: Daai = Depends(daai), db: Session = Depends(get_db)):
    tz = body.tz.strip()
    if ZONES and tz not in ZONES:
        raise HTTPException(400, "unknown time zone")
    weekly = {}
    for day, ranges in body.weekly.items():
        if day not in DAYS:
            raise HTTPException(400, "bad day")
        if len(ranges) > 6:
            raise HTTPException(400, "too many ranges")
        clean = []
        for r in ranges:
            if len(r) != 2 or not all(HHMM.match(x) for x in r) or r[0] == "24:00" or r[0] >= r[1]:
                raise HTTPException(400, "bad hours")
            clean.append([r[0], r[1]])
        clean.sort()
        if any(clean[i][1] > clean[i + 1][0] for i in range(len(clean) - 1)):
            raise HTTPException(400, "hours overlap")
        if clean:
            weekly[day] = clean
    today = utcnow().date()
    days_off = []
    for s in body.days_off:
        try:
            d = date.fromisoformat(s)
        except ValueError:
            raise HTTPException(400, "bad date")
        if today - timedelta(days=1) <= d <= today + timedelta(days=365):
            days_off.append(d.isoformat())
    row = db.get(DaaiSchedule, me.id) or DaaiSchedule(daai_id=me.id)
    row.tz, row.weekly, row.days_off, row.paused, row.updated_at = tz, weekly, sorted(set(days_off)), body.paused, utcnow()
    db.add(row)
    db.commit()
    return _schedule_out(row)


@router.get("/daai/bookings")
def my_daai_bookings(me: Daai = Depends(daai), db: Session = Depends(get_db)):
    """Upcoming bookings (soonest first) and those of the last 30 days (newest first)."""
    now = utcnow()
    rows = db.scalars(select(Booking).where(Booking.daai_id == me.id, Booking.starts_at >= now - timedelta(days=30))
                      .order_by(Booking.starts_at)).all()
    for b in rows:
        _refresh(db, b, now)
    upcoming = [daai_view(db, b, now) for b in rows if b.status == "booked"]
    past = [daai_view(db, b, now) for b in reversed(rows) if b.status != "booked"]
    return {"upcoming": upcoming, "past": past[:50]}


def booked_soon(db: Session, d: Daai) -> list[dict]:
    """This da'i's bookings that start within QUIET_BEFORE or are running now (for the calls tab)."""
    now = utcnow()
    rows = db.scalars(select(Booking).where(Booking.daai_id == d.id, Booking.status == "booked",
                                            Booking.starts_at <= now + QUIET_BEFORE,
                                            Booking.starts_at >= now - timedelta(hours=1))).all()
    return [daai_view(db, b, now) for b in rows if _refresh(db, b, now).status == "booked"]


def bookings_today(db: Session, d: Daai) -> int:
    """How many booked calls this da'i has in the next 24 hours (the badge on the console's schedule tab)."""
    now = utcnow()
    return db.scalar(select(func.count()).select_from(Booking).where(
        Booking.daai_id == d.id, Booking.status == "booked", Booking.starts_at >= now - GRACE,
        Booking.starts_at < now + timedelta(hours=24))) or 0


def booking_for_call(db: Session, call_id: int) -> dict | None:
    """The booking a call was started from, for the da'i's call screen (end time, whether the seeker came)."""
    b = db.scalar(select(Booking).where(Booking.call_id == call_id))
    if not b:
        return None
    now = utcnow()
    return {**daai_view(db, b, now), "no_show_from": iso(b.starts_at + GRACE)}


def _own_booking(db: Session, bid: int, me: Daai) -> Booking:
    b = db.get(Booking, bid)
    if not b or b.daai_id != me.id:
        raise HTTPException(404, "not found")
    return _refresh(db, b)


@router.post("/daai/bookings/{bid}/start")
def start_booking(bid: int, me: Daai = Depends(daai), db: Session = Depends(get_db)):
    """Opens the call room for this booking; the seeker's page notices and joins. Returns {call_id}."""
    b = _own_booking(db, bid, me)
    if b.call_id:
        call = db.get(CallRequest, b.call_id)
        if call and call.status == "accepted":
            return {"call_id": call.id}
    if not daai_view(db, b)["can_start"]:
        raise HTTPException(409, "not time yet")
    other = db.scalar(select(CallRequest.id).where(CallRequest.daai_id == me.id, CallRequest.status == "accepted"))
    if other:
        raise HTTPException(409, "finish your current call first")
    now = utcnow()
    call = CallRequest(session_id=b.session_id, lang=b.lang, referral_id=b.referral_id, daai_pref=me.id,
                       status="accepted", daai_id=me.id, accepted_at=now)
    db.add(call)
    db.flush()
    b.call_id = call.id
    db.commit()
    return {"call_id": call.id}


class CancelIn(BaseModel):
    note: str = Field(default="", max_length=300)


@router.post("/daai/bookings/{bid}/cancel")
def daai_cancel_booking(bid: int, body: CancelIn, me: Daai = Depends(daai), db: Session = Depends(get_db)):
    b = _own_booking(db, bid, me)
    if b.status != "booked" or b.call_id:
        raise HTTPException(409, "can't cancel now")
    b.status, b.cancelled_by, b.cancel_note = "cancelled", "daai", body.note.strip()
    _free(db, b)
    db.commit()
    return daai_view(db, b)


@router.post("/daai/bookings/{bid}/no-show")
def seeker_no_show(bid: int, me: Daai = Depends(daai), db: Session = Depends(get_db)):
    """The da'i waited and the seeker didn't come: allowed once the grace time has passed."""
    b = _own_booking(db, bid, me)
    if b.status == "booked":
        if utcnow() < b.starts_at + GRACE:
            raise HTTPException(409, "not time yet")
        b.status, b.missed_by = "missed", "seeker"
        call = db.get(CallRequest, b.call_id) if b.call_id else None
        if call and call.status == "accepted":
            call.status, call.ended_at = "ended", utcnow()
        db.commit()
    return daai_view(db, b)


# ---------------------------------------------------------------------------
# Seeker: da'is with hours, free slots, book, my bookings, join, cancel
# ---------------------------------------------------------------------------

def _candidates(db: Session, lang: str, gender: str, daai_id: int | None) -> list[Daai]:
    q = select(Daai).where(Daai.role == "daai").order_by(Daai.id)
    if daai_id is not None:
        q = q.where(Daai.id == daai_id)
    return [d for d in db.scalars(q).all()
            if bookable(db, d) and (not lang or lang in (d.languages or [])) and (not gender or d.gender == gender)]


@router.get("/booking/daais")
def bookable_daais(lang: str = "", ui: str = "ar", db: Session = Depends(get_db)):
    """Da'is who take bookings in `lang`, with their next free time (soonest first)."""
    out = []
    for d in _candidates(db, lang, "", None):
        slots = free_slots(db, d)
        out.append({**d.public("ar" if ui == "ar" else "en"), "bio": d.bio if ui == "ar" else (d.bio_en or d.bio),
                    "next_slot": iso(slots[0]) if slots else None})
    out.sort(key=lambda x: (x["next_slot"] is None, x["next_slot"] or ""))
    return out


@router.get("/booking/slots")
def booking_slots(lang: str, gender: str = "", daai_id: int | None = None, minutes: int = UNIT,
                  replaces: int | None = None, me: SeekerSession | None = Depends(optional_seeker),
                  db: Session = Depends(get_db)):
    """Free start times for one da'i, or (no daai_id) for anyone who matches: [{starts_at, daais}] with the count
    of da'is free then. Times are UTC; the page shows them in the viewer's zone. `replaces`: one of my bookings
    I'm moving, whose own time then counts as free."""
    if minutes not in LENGTHS:
        raise HTTPException(400, "bad length")
    if gender not in ("", "m", "f"):
        raise HTTPException(400, "bad gender preference")
    moving = db.get(Booking, replaces) if replaces is not None else None
    ignore = moving.id if moving and me and moving.session_id == me.id else None
    merged: dict[datetime, int] = {}
    for d in _candidates(db, lang, gender, daai_id):
        for at in free_slots(db, d, minutes, ignore=ignore):
            merged[at] = merged.get(at, 0) + 1
    return {"minutes": minutes, "days_ahead": DAYS_AHEAD, "min_notice_hours": int(MIN_NOTICE.total_seconds() // 3600),
            "slots": [{"starts_at": iso(at), "daais": n} for at, n in sorted(merged.items())]}


class BookIn(BaseModel):
    starts_at: str
    minutes: int = UNIT
    lang: str
    gender_pref: str = ""
    daai_id: int | None = None          # None: whoever matches and is free then
    referral_id: int | None = None
    note: str = Field(default="", max_length=300)
    replaces: int | None = None         # reschedule: this booking of mine is cancelled once the new one is made


def _upcoming(db: Session, sid: str) -> list[Booking]:
    rows = db.scalars(select(Booking).where(Booking.session_id == sid, Booking.status == "booked")).all()
    return [b for b in rows if _refresh(db, b).status == "booked"]


@router.post("/bookings")
def book(body: BookIn, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    if not is_account(db, me.id):
        raise HTTPException(403, "sign in to book")
    if body.minutes not in LENGTHS:
        raise HTTPException(400, "bad length")
    if body.gender_pref not in ("", "m", "f"):
        raise HTTPException(400, "bad gender preference")
    at = _parse_utc(body.starts_at)
    if body.referral_id:
        ref = db.get(Referral, body.referral_id)
        if not ref or ref.session_id != me.id:
            raise HTTPException(404, "referral not found")
    old = None
    if body.replaces is not None:
        old = db.get(Booking, body.replaces)
        if not old or old.session_id != me.id:
            raise HTTPException(404, "not found")
        if not seeker_view(db, _refresh(db, old))["can_cancel"]:
            raise HTTPException(409, "can't cancel now")
        if body.referral_id is None:
            body.referral_id = old.referral_id   # a card shared for the old time stays with the new one
        if not body.note:
            body.note = old.note
    mine = [b for b in _upcoming(db, me.id) if not old or b.id != old.id]
    if len(mine) >= MAX_UPCOMING:
        raise HTTPException(409, "too many bookings")
    end = at + timedelta(minutes=body.minutes)
    if any(b.starts_at < end and at < b.starts_at + timedelta(minutes=b.minutes) for b in mine):
        raise HTTPException(409, "you already have a booking then")
    people = _candidates(db, body.lang, body.gender_pref, body.daai_id)
    if body.daai_id is not None and not people:
        raise HTTPException(404, "da'i not found")
    # With "anyone", the da'i with the fewest upcoming bookings gets it, to spread the load.
    load = dict(db.execute(select(Booking.daai_id, func.count()).where(Booking.status == "booked", Booking.starts_at >= utcnow())
                           .group_by(Booking.daai_id)).all())
    for d in sorted(people, key=lambda p: load.get(p.id, 0)):
        if old:
            _free(db, old)   # the old time counts as free (e.g. extending 30 to 60 minutes); a rollback restores it
            db.flush()
        if at not in free_slots(db, d, body.minutes):
            db.rollback()
            continue
        b = Booking(session_id=me.id, daai_id=d.id, starts_at=at, minutes=body.minutes, lang=body.lang,
                    note=body.note.strip(), referral_id=body.referral_id)
        db.add(b)
        try:
            db.flush()
            for k in range(body.minutes // UNIT):
                db.add(BookingBlock(daai_id=d.id, starts_at=at + timedelta(minutes=UNIT * k), booking_id=b.id))
            if old:
                old.status, old.cancelled_by, old.rescheduled_to = "cancelled", "seeker", b.id
            db.commit()
        except IntegrityError:
            db.rollback()   # someone took this time a moment ago; try the next da'i
            continue
        return seeker_view(db, b)
    raise HTTPException(409, "slot taken")


@router.get("/bookings")
def my_bookings(me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    now = utcnow()
    rows = db.scalars(select(Booking).where(Booking.session_id == me.id).order_by(Booking.starts_at)).all()
    for b in rows:
        _refresh(db, b, now)
    upcoming = [seeker_view(db, b, now) for b in rows if b.status == "booked"]
    past = [seeker_view(db, b, now) for b in reversed(rows) if b.status != "booked"]
    return {"upcoming": upcoming, "past": past[:30], "signed_in": is_account(db, me.id), "max_upcoming": MAX_UPCOMING}


def _mine(db: Session, bid: int, me: SeekerSession) -> Booking:
    b = db.get(Booking, bid)
    if not b or b.session_id != me.id:
        raise HTTPException(404, "not found")
    return _refresh(db, b)


@router.get("/bookings/{bid}")
def booking_status(bid: int, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    return seeker_view(db, _mine(db, bid, me))


@router.post("/bookings/{bid}/join")
def join_booking(bid: int, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    """The seeker is here and waiting. Once the da'i presses Start, the view carries call_id."""
    b = _mine(db, bid, me)
    if not seeker_view(db, b)["can_join"]:
        raise HTTPException(409, "not time yet")
    if not b.seeker_ready_at:
        b.seeker_ready_at = utcnow()
        db.commit()
    return seeker_view(db, b)


@router.post("/bookings/{bid}/cancel")
def cancel_booking(bid: int, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    b = _mine(db, bid, me)
    if b.status != "booked" or b.call_id or utcnow() >= b.starts_at:
        raise HTTPException(409, "can't cancel now")
    b.status, b.cancelled_by = "cancelled", "seeker"
    _free(db, b)
    db.commit()
    return seeker_view(db, b)
