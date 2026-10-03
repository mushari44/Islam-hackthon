"""Community API: groups led by da'is (with the @سبيلي assistant) and in-person meetups. Owner: Mushari.

Safety rules built in: no direct messages between seekers, nicknames only,
every message moderated, the leader can delete posts and mute members,
meetups only at public venues, RSVPs collect a nickname and nothing else.

Contract used by frontend/src/features/community (see docs/API.md).
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.db import SessionLocal, get_db, iso, utcnow
from ..auth.public import Daai, SeekerSession, daai, optional_daai, optional_seeker, seeker
from ..rag.public import answer_in_group
from . import moderation
from .models import RSVP, Group, GroupMember, GroupMessage, Meetup

router = APIRouter(prefix="/api")
log = logging.getLogger("sabeeli.community")

BOT_NAME = {"ar": "سَبِيلي (مساعد آلي)", "en": "Sabeeli (AI assistant)"}


def booking_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _member_count(db: Session, gid: int) -> int:
    return db.scalar(select(func.count()).select_from(GroupMember)
                     .where(GroupMember.group_id == gid, GroupMember.left.is_(False))) or 0


def _group_view(db: Session, g: Group, lang: str, me: GroupMember | None = None) -> dict:
    leader = db.get(Daai, g.leader_id)
    return {"id": g.id, "title": g.title, "description": g.description, "lang": g.lang, "country": g.country,
            "city": g.city, "audience": g.audience, "active": g.active, "members": _member_count(db, g.id),
            "leader": leader.public(lang) if leader else None, "is_demo": g.is_demo,
            "membership": {"id": me.id, "nickname": me.nickname, "muted": me.muted} if me else None}


def _message_view(m: GroupMessage) -> dict:
    return {"id": m.id, "author_type": m.author_type, "author": m.author_name, "member_id": m.member_id,
            "text": "" if m.deleted else m.text, "deleted": m.deleted, "payload": {} if m.deleted else m.payload,
            "reply_to": m.reply_to, "needs_leader": m.needs_leader, "at": iso(m.created_at)}


def _membership(db: Session, gid: int, sid: str) -> GroupMember | None:
    return db.scalars(select(GroupMember).where(GroupMember.group_id == gid, GroupMember.session_id == sid,
                                                GroupMember.left.is_(False))).first()


def _bot_reply(group_id: int, question: str, reply_to: int, lang: str) -> None:
    """Runs after the response: answers an @سبيلي mention with the same cited pipeline."""
    db = SessionLocal()
    try:
        result = answer_in_group(question, lang)
        text = " ".join(s["text"] for s in result.get("segments", []))[:4000]
        flag = result.get("level") in ("C", "D") or result.get("kind") == "abstain"
        db.add(GroupMessage(group_id=group_id, author_type="bot", author_name=BOT_NAME.get(lang, BOT_NAME["en"]),
                            text=text, reply_to=reply_to, needs_leader=flag,
                            payload={k: result.get(k) for k in ("segments", "cards", "sources", "notices", "kind",
                                                                "level", "mode", "quote_check", "lang")}))
        db.commit()
    except Exception:  # noqa: BLE001 - the group must not break if the assistant fails
        log.exception("group assistant failed")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Groups: seekers
# ---------------------------------------------------------------------------

@router.get("/groups")
def list_groups(lang: str = "", country: str = "", city: str = "", ui: str = "ar",
                me: SeekerSession | None = Depends(optional_seeker), db: Session = Depends(get_db)):
    q = select(Group).where(Group.active.is_(True))
    if lang:
        q = q.where(Group.lang == lang)
    if country:
        q = q.where(Group.country == country)
    if city:
        q = q.where(Group.city == city)
    groups = db.scalars(q.order_by(Group.id)).all()
    return [_group_view(db, g, ui, _membership(db, g.id, me.id) if me else None) for g in groups]


@router.get("/community/places")
def community_places(db: Session = Depends(get_db)):
    """Countries (ISO codes) and their cities that have an active group or an upcoming meetup, for the filters."""
    rows = db.execute(select(Group.country, Group.city).where(Group.active.is_(True))).all()
    rows += db.execute(select(Meetup.country, Meetup.city).where(
        Meetup.status == "open", Meetup.starts_at >= utcnow() - timedelta(hours=3))).all()
    places: dict[str, set[str]] = {}
    for country, city in rows:
        if country:
            places.setdefault(country, set())
            if city:
                places[country].add(city)
    order = sorted(places, key=lambda c: (c != "SA", c))     # Saudi Arabia first
    return [{"country": c, "cities": sorted(places[c])} for c in order]


@router.get("/groups/{gid}")
def get_group(gid: int, ui: str = "ar", me: SeekerSession | None = Depends(optional_seeker),
              db: Session = Depends(get_db)):
    g = db.get(Group, gid)
    if not g or not g.active:
        raise HTTPException(404, "not found")
    return _group_view(db, g, ui, _membership(db, gid, me.id) if me else None)


class JoinIn(BaseModel):
    nickname: str = Field(min_length=2, max_length=40)
    accept_rules: bool


@router.post("/groups/{gid}/join")
def join_group(gid: int, body: JoinIn, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    g = db.get(Group, gid)
    if not g or not g.active:
        raise HTTPException(404, "not found")
    if not body.accept_rules:
        raise HTTPException(400, "please accept the group rules")
    nick = moderation.clean_nickname(body.nickname)
    if len(nick) < 2 or not moderation.check(nick, None).ok:
        raise HTTPException(400, "choose another nickname")
    taken = db.scalars(select(GroupMember).where(GroupMember.group_id == gid, GroupMember.nickname == nick,
                                                 GroupMember.left.is_(False), GroupMember.session_id != me.id)).first()
    if taken:
        raise HTTPException(409, "nickname taken in this group")
    existing = _membership(db, gid, me.id)
    if existing:
        existing.nickname = nick
    else:
        db.add(GroupMember(group_id=gid, session_id=me.id, nickname=nick))
    db.commit()
    return _group_view(db, g, "ar", _membership(db, gid, me.id))


@router.post("/groups/{gid}/leave")
def leave_group(gid: int, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    m = _membership(db, gid, me.id)
    if m:
        m.left = True
        db.commit()
    return {"ok": True}


@router.get("/groups/{gid}/messages")
def group_messages(gid: int, after: int = 0, me: SeekerSession | None = Depends(optional_seeker),
                   lead: Daai | None = Depends(optional_daai), db: Session = Depends(get_db)):
    g = db.get(Group, gid)
    if not g or (not g.active and not (lead and lead.id == g.leader_id)):
        raise HTTPException(404, "not found")
    allowed = (lead and lead.id == g.leader_id) or (me and _membership(db, gid, me.id))
    if not allowed:
        raise HTTPException(403, "join the group to read its messages")
    msgs = db.scalars(select(GroupMessage).where(GroupMessage.group_id == gid, GroupMessage.id > after)
                      .order_by(GroupMessage.id).limit(200)).all()
    return [_message_view(m) for m in msgs]


class PostIn(BaseModel):
    text: str = Field(max_length=2000)
    lang: str = "ar"


@router.post("/groups/{gid}/messages")
def post_message(gid: int, body: PostIn, tasks: BackgroundTasks, me: SeekerSession = Depends(seeker),
                 db: Session = Depends(get_db)):
    g = db.get(Group, gid)
    member = _membership(db, gid, me.id)
    if not g or not g.active or not member:
        raise HTTPException(403, "join the group first")
    if member.muted:
        raise HTTPException(403, "muted")
    since = (utcnow() - member.last_post_at).total_seconds() if member.last_post_at else None
    verdict = moderation.check(body.text, since)
    if not verdict.ok:
        if verdict.reason == "abuse":
            member.strikes += 1
            if member.strikes >= moderation.STRIKES_TO_MUTE:
                member.muted = True
            db.commit()
        raise HTTPException(422, verdict.reason)
    msg = GroupMessage(group_id=gid, author_type="seeker", author_name=member.nickname, member_id=member.id,
                       text=verdict.text)
    member.last_post_at = utcnow()
    db.add(msg)
    db.commit()
    if moderation.mentions_bot(verdict.text):
        question = moderation.strip_mention(verdict.text)
        if question:
            tasks.add_task(_bot_reply, gid, question, msg.id, "ar" if body.lang == "ar" else "en")
    return {**_message_view(msg), "redacted": verdict.redacted}


# ---------------------------------------------------------------------------
# Groups: leaders (da'is)
# ---------------------------------------------------------------------------

class GroupIn(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(default="", max_length=2000)
    lang: str = "ar"
    country: str = ""
    city: str = ""
    audience: str = "all"


@router.get("/daai/groups")
def my_groups(lead: Daai = Depends(daai), db: Session = Depends(get_db)):
    groups = db.scalars(select(Group).where(Group.leader_id == lead.id).order_by(Group.id)).all()
    out = []
    for g in groups:
        view = _group_view(db, g, "ar")
        view["needs_leader"] = db.scalar(select(func.count()).select_from(GroupMessage).where(
            GroupMessage.group_id == g.id, GroupMessage.needs_leader.is_(True), GroupMessage.deleted.is_(False))) or 0
        out.append(view)
    return out


@router.post("/daai/groups")
def create_group(body: GroupIn, lead: Daai = Depends(daai), db: Session = Depends(get_db)):
    if body.audience not in ("all", "women", "men"):
        raise HTTPException(400, "bad audience")
    g = Group(title=body.title.strip(), description=body.description.strip(), lang=body.lang, country=body.country,
              city=body.city, audience=body.audience, leader_id=lead.id)
    db.add(g)
    db.commit()
    return _group_view(db, g, "ar")


def _own_group(db: Session, gid: int, lead: Daai) -> Group:
    g = db.get(Group, gid)
    if not g or g.leader_id != lead.id:
        raise HTTPException(404, "not found")
    return g


@router.post("/daai/groups/{gid}/messages")
def leader_post(gid: int, body: PostIn, lead: Daai = Depends(daai), db: Session = Depends(get_db)):
    g = _own_group(db, gid, lead)
    text = (body.text or "").strip()[:2000]
    if not text:
        raise HTTPException(400, "empty")
    msg = GroupMessage(group_id=g.id, author_type="daai", author_name=lead.display_name, daai_id=lead.id, text=text)
    db.add(msg)
    db.commit()
    return _message_view(msg)


@router.post("/daai/groups/{gid}/messages/{mid}/delete")
def delete_message(gid: int, mid: int, lead: Daai = Depends(daai), db: Session = Depends(get_db)):
    _own_group(db, gid, lead)
    m = db.get(GroupMessage, mid)
    if not m or m.group_id != gid:
        raise HTTPException(404, "not found")
    m.deleted = True
    db.commit()
    return {"ok": True}


@router.post("/daai/groups/{gid}/messages/{mid}/resolve")
def resolve_flag(gid: int, mid: int, lead: Daai = Depends(daai), db: Session = Depends(get_db)):
    _own_group(db, gid, lead)
    m = db.get(GroupMessage, mid)
    if m and m.group_id == gid:
        m.needs_leader = False
        db.commit()
    return {"ok": True}


class MuteIn(BaseModel):
    muted: bool


@router.post("/daai/groups/{gid}/members/{member_id}/mute")
def mute_member(gid: int, member_id: int, body: MuteIn, lead: Daai = Depends(daai), db: Session = Depends(get_db)):
    _own_group(db, gid, lead)
    m = db.get(GroupMember, member_id)
    if not m or m.group_id != gid:
        raise HTTPException(404, "not found")
    m.muted = body.muted
    db.commit()
    return {"ok": True, "muted": m.muted}


# ---------------------------------------------------------------------------
# Meetups
# ---------------------------------------------------------------------------

def _meetup_view(db: Session, m: Meetup, lang: str, sid: str | None = None) -> dict:
    host = db.get(Daai, m.host_id)
    going = db.scalar(select(func.count()).select_from(RSVP).where(RSVP.meetup_id == m.id, RSVP.cancelled.is_(False))) or 0
    mine = None
    if sid:
        r = db.scalars(select(RSVP).where(RSVP.meetup_id == m.id, RSVP.session_id == sid, RSVP.cancelled.is_(False))).first()
        mine = {"code": r.code, "nickname": r.nickname} if r else None
    return {"id": m.id, "title": m.title, "description": m.description, "lang": m.lang, "country": m.country,
            "city": m.city, "venue": m.venue, "starts_at": iso(m.starts_at), "duration_min": m.duration_min,
            "capacity": m.capacity, "going": going, "spots_left": max(0, m.capacity - going), "audience": m.audience,
            "registration": m.registration, "age_group": m.age_group, "series": m.series,
            "host": host.public(lang) if host else None, "group_id": m.group_id, "status": m.status,
            "is_demo": m.is_demo, "my_rsvp": mine}


@router.get("/meetups")
def list_meetups(country: str = "", city: str = "", lang: str = "", ui: str = "ar",
                 registration: str = "", age: str = "", series: str = "",
                 me: SeekerSession | None = Depends(optional_seeker), db: Session = Depends(get_db)):
    q = select(Meetup).where(Meetup.status == "open", Meetup.starts_at >= utcnow() - timedelta(hours=3))
    if country:
        q = q.where(Meetup.country == country)
    if city:
        q = q.where(Meetup.city == city)
    if lang:
        q = q.where(Meetup.lang == lang)
    if registration:
        q = q.where(Meetup.registration == registration)
    if age:   # a meetup for all ages also suits every age group
        q = q.where(Meetup.age_group.in_([age, "all"]))
    if series:
        q = q.where(Meetup.series == series)
    return [_meetup_view(db, m, ui, me.id if me else None) for m in db.scalars(q.order_by(Meetup.starts_at)).all()]


class RsvpIn(BaseModel):
    nickname: str = Field(min_length=2, max_length=40)
    confirm_audience: bool = False


@router.post("/meetups/{mid}/rsvp")
def rsvp(mid: int, body: RsvpIn, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    m = db.get(Meetup, mid)
    if not m or m.status != "open":
        raise HTTPException(404, "not found")
    if (m.audience in ("women", "men") or m.age_group == "kids") and not body.confirm_audience:
        raise HTTPException(400, "please confirm the audience of this meetup")
    existing = db.scalars(select(RSVP).where(RSVP.meetup_id == mid, RSVP.session_id == me.id,
                                             RSVP.cancelled.is_(False))).first()
    if existing:
        return _meetup_view(db, m, "ar", me.id)
    going = db.scalar(select(func.count()).select_from(RSVP).where(RSVP.meetup_id == mid, RSVP.cancelled.is_(False))) or 0
    if going >= m.capacity and m.registration == "required":   # walk-in events only count who joined
        raise HTTPException(409, "full")
    nick = moderation.clean_nickname(body.nickname)
    if len(nick) < 2:
        raise HTTPException(400, "choose another nickname")
    db.add(RSVP(meetup_id=mid, session_id=me.id, nickname=nick, code=booking_code()))
    db.commit()
    return _meetup_view(db, m, "ar", me.id)


@router.post("/meetups/{mid}/cancel-rsvp")
def cancel_rsvp(mid: int, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    r = db.scalars(select(RSVP).where(RSVP.meetup_id == mid, RSVP.session_id == me.id, RSVP.cancelled.is_(False))).first()
    if r:
        r.cancelled = True
        db.commit()
    return {"ok": True}


def _ics_time(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")


@router.get("/meetups/{mid}/ics")
def meetup_ics(mid: int, db: Session = Depends(get_db)):
    m = db.get(Meetup, mid)
    if not m:
        raise HTTPException(404, "not found")

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")

    body = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Sabeeli//Meetups//AR", "BEGIN:VEVENT",
        f"UID:sabeeli-meetup-{m.id}@sabeeli", f"DTSTAMP:{_ics_time(utcnow())}",
        f"DTSTART:{_ics_time(m.starts_at)}", f"DTEND:{_ics_time(m.starts_at + timedelta(minutes=m.duration_min))}",
        f"SUMMARY:{esc(m.title)}", f"LOCATION:{esc(m.venue + ', ' + m.city)}", f"DESCRIPTION:{esc(m.description)}",
        "END:VEVENT", "END:VCALENDAR", ""])
    return Response(body, media_type="text/calendar",
                    headers={"Content-Disposition": f'attachment; filename="sabeeli-meetup-{m.id}.ics"'})


class MeetupIn(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(default="", max_length=2000)
    lang: str = "ar"
    country: str = ""
    city: str = Field(min_length=2, max_length=64)
    venue: str = Field(min_length=3, max_length=200)
    starts_at: datetime
    duration_min: int = Field(default=90, ge=15, le=480)
    capacity: int = Field(default=20, ge=2, le=500)
    audience: str = "all"
    registration: str = "required"
    age_group: str = "all"
    series: str = ""
    group_id: int | None = None
    public_venue: bool = False


REGISTRATION = ("required", "open")
AGE_GROUPS = ("all", "kids", "youth", "adults", "seniors")
SERIES = ("", "qawl_amal", "ramadan")


@router.get("/daai/meetups")
def my_meetups(lead: Daai = Depends(daai), db: Session = Depends(get_db)):
    out = []
    for m in db.scalars(select(Meetup).where(Meetup.host_id == lead.id).order_by(Meetup.starts_at)).all():
        view = _meetup_view(db, m, "ar")
        view["attendees"] = [r.nickname for r in db.scalars(select(RSVP).where(RSVP.meetup_id == m.id,
                                                                                RSVP.cancelled.is_(False))).all()]
        out.append(view)
    return out


@router.post("/daai/meetups")
def create_meetup(body: MeetupIn, lead: Daai = Depends(daai), db: Session = Depends(get_db)):
    if not body.public_venue:
        raise HTTPException(400, "meetups must be at a public venue")
    if body.audience not in ("all", "women", "men", "families"):
        raise HTTPException(400, "bad audience")
    if body.registration not in REGISTRATION or body.age_group not in AGE_GROUPS or body.series not in SERIES:
        raise HTTPException(400, "bad meetup type")
    starts = body.starts_at if body.starts_at.tzinfo is None else \
        body.starts_at.astimezone(timezone.utc).replace(tzinfo=None)
    if body.group_id:
        g = db.get(Group, body.group_id)
        if not g or g.leader_id != lead.id:
            raise HTTPException(400, "you can only link your own group")
    m = Meetup(title=body.title.strip(), description=body.description.strip(), lang=body.lang, country=body.country,
               city=body.city.strip(), venue=body.venue.strip(), starts_at=starts, duration_min=body.duration_min,
               capacity=body.capacity, audience=body.audience, registration=body.registration,
               age_group=body.age_group, series=body.series, host_id=lead.id, group_id=body.group_id)
    db.add(m)
    db.commit()
    return _meetup_view(db, m, "ar")


@router.post("/daai/meetups/{mid}/cancel")
def cancel_meetup(mid: int, lead: Daai = Depends(daai), db: Session = Depends(get_db)):
    m = db.get(Meetup, mid)
    if not m or m.host_id != lead.id:
        raise HTTPException(404, "not found")
    m.status = "cancelled"
    db.commit()
    return {"ok": True}
