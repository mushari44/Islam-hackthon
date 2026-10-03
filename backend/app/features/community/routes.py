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
# Posted when the assistant fails, so the asker isn't left waiting and the leader is asked to step in.
BOT_FAILED = {"ar": "تعذّر على المساعد الإجابة الآن. نبّهنا قائد المجموعة ليجيب عن سؤالك.",
              "en": "The assistant couldn't answer right now. We've asked the group leader to reply."}


LANG = r"^[a-z]{2,3}$"    # interface or content language code, e.g. ar, en, fr
MESSAGES_PAGE = 200


def _ui(ui: str) -> str:
    """Leader and host names exist in Arabic and English only."""
    return "en" if ui == "en" else "ar"


def booking_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _member_count(db: Session, gid: int) -> int:
    return db.scalar(select(func.count()).select_from(GroupMember)
                     .where(GroupMember.group_id == gid, GroupMember.left.is_(False))) or 0


def _member_counts(db: Session, gids: list[int]) -> dict[int, int]:
    """Member counts for many groups in one query (the group list used to run one per group)."""
    if not gids:
        return {}
    rows = db.execute(select(GroupMember.group_id, func.count()).where(
        GroupMember.group_id.in_(gids), GroupMember.left.is_(False)).group_by(GroupMember.group_id)).all()
    return dict(rows)


def _group_view(db: Session, g: Group, lang: str, me: GroupMember | None = None, members: int | None = None) -> dict:
    leader = db.get(Daai, g.leader_id)
    return {"id": g.id, "title": g.title, "description": g.description, "lang": g.lang, "country": g.country,
            "city": g.city, "audience": g.audience, "active": g.active,
            "members": _member_count(db, g.id) if members is None else members,
            "leader": leader.public(_ui(lang)) if leader else None, "is_demo": g.is_demo,
            "membership": {"id": me.id, "nickname": me.nickname, "muted": me.muted} if me else None}


def _message_view(m: GroupMessage) -> dict:
    return {"id": m.id, "author_type": m.author_type, "author": m.author_name, "member_id": m.member_id,
            "text": "" if m.deleted else m.text, "deleted": m.deleted, "payload": {} if m.deleted else m.payload,
            "reply_to": m.reply_to, "needs_leader": m.needs_leader, "at": iso(m.created_at)}


def _membership(db: Session, gid: int, sid: str) -> GroupMember | None:
    return db.scalars(select(GroupMember).where(GroupMember.group_id == gid, GroupMember.session_id == sid,
                                                GroupMember.left.is_(False))).first()


def _past_membership(db: Session, gid: int, sid: str) -> GroupMember | None:
    """The newest membership this browser left, so rejoining keeps a mute and strikes."""
    return db.scalars(select(GroupMember).where(GroupMember.group_id == gid, GroupMember.session_id == sid,
                                                GroupMember.left.is_(True))
                      .order_by(GroupMember.id.desc())).first()


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
        db.rollback()
        try:
            db.add(GroupMessage(group_id=group_id, author_type="bot", author_name=BOT_NAME.get(lang, BOT_NAME["en"]),
                                text=BOT_FAILED.get(lang, BOT_FAILED["en"]), reply_to=reply_to, needs_leader=True,
                                payload={}))
            db.commit()
        except Exception:  # noqa: BLE001
            log.exception("could not post the assistant's failure notice")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Groups: seekers
# ---------------------------------------------------------------------------

@router.get("/groups")
def list_groups(lang: str = "", country: str = "", ui: str = "ar",
                me: SeekerSession | None = Depends(optional_seeker), db: Session = Depends(get_db)):
    q = select(Group).where(Group.active.is_(True))
    if lang:
        q = q.where(Group.lang == lang)
    if country:
        q = q.where(Group.country == country)
    groups = db.scalars(q.order_by(Group.id)).all()
    counts = _member_counts(db, [g.id for g in groups])
    mine: dict[int, GroupMember] = {}
    if me and groups:
        mine = {m.group_id: m for m in db.scalars(select(GroupMember).where(
            GroupMember.session_id == me.id, GroupMember.left.is_(False),
            GroupMember.group_id.in_([g.id for g in groups]))).all()}
    return [_group_view(db, g, ui, mine.get(g.id), counts.get(g.id, 0)) for g in groups]


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
    confirm_audience: bool = False


@router.post("/groups/{gid}/join")
def join_group(gid: int, body: JoinIn, ui: str = "ar", me: SeekerSession = Depends(seeker),
               db: Session = Depends(get_db)):
    g = db.get(Group, gid)
    if not g or not g.active:
        raise HTTPException(404, "not found")
    if not body.accept_rules:
        raise HTTPException(400, "please accept the group rules")
    if g.audience in ("women", "men") and not body.confirm_audience:
        raise HTTPException(400, "please confirm the audience of this group")
    nick = moderation.clean_nickname(body.nickname)
    if not moderation.nickname_ok(nick):
        raise HTTPException(400, "choose another nickname")
    taken = db.scalars(select(GroupMember).where(GroupMember.group_id == gid, GroupMember.nickname == nick,
                                                 GroupMember.left.is_(False), GroupMember.session_id != me.id)).first()
    if taken:
        raise HTTPException(409, "nickname taken in this group")
    existing = _membership(db, gid, me.id) or _past_membership(db, gid, me.id)
    if existing:
        existing.nickname, existing.left = nick, False
    else:
        db.add(GroupMember(group_id=gid, session_id=me.id, nickname=nick))
    db.commit()
    return _group_view(db, g, ui, _membership(db, gid, me.id))


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
    q = select(GroupMessage).where(GroupMessage.group_id == gid)
    if after > 0:
        msgs = db.scalars(q.where(GroupMessage.id > after).order_by(GroupMessage.id).limit(MESSAGES_PAGE)).all()
    else:   # first load: the newest page, so a long conversation opens at its end
        msgs = list(reversed(db.scalars(q.order_by(GroupMessage.id.desc()).limit(MESSAGES_PAGE)).all()))
    return [_message_view(m) for m in msgs]


class PostIn(BaseModel):
    text: str = Field(max_length=2000)
    lang: str = Field(default="ar", max_length=8)


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
    lang: str = Field(default="ar", pattern=LANG)
    country: str = Field(default="", max_length=64)
    city: str = Field(default="", max_length=64)
    audience: str = "all"


@router.get("/daai/groups")
def my_groups(ui: str = "ar", lead: Daai = Depends(daai), db: Session = Depends(get_db)):
    groups = db.scalars(select(Group).where(Group.leader_id == lead.id).order_by(Group.id)).all()
    gids = [g.id for g in groups]
    counts = _member_counts(db, gids)
    flagged = dict(db.execute(select(GroupMessage.group_id, func.count()).where(
        GroupMessage.group_id.in_(gids), GroupMessage.needs_leader.is_(True), GroupMessage.deleted.is_(False))
        .group_by(GroupMessage.group_id)).all()) if gids else {}
    return [{**_group_view(db, g, ui, members=counts.get(g.id, 0)), "needs_leader": flagged.get(g.id, 0)}
            for g in groups]


@router.post("/daai/groups")
def create_group(body: GroupIn, ui: str = "ar", lead: Daai = Depends(daai), db: Session = Depends(get_db)):
    if body.audience not in ("all", "women", "men"):
        raise HTTPException(400, "bad audience")
    g = Group(title=body.title.strip(), description=body.description.strip(), lang=body.lang,
              country=body.country.strip(), city=body.city.strip(), audience=body.audience, leader_id=lead.id)
    db.add(g)
    db.commit()
    return _group_view(db, g, ui)


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
    # The leader's name in the group's own language, as the seeded welcome messages do.
    name = lead.display_name if g.lang == "ar" else (lead.display_name_en or lead.display_name)
    msg = GroupMessage(group_id=g.id, author_type="daai", author_name=name, daai_id=lead.id, text=text)
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

def _going_counts(db: Session, mids: list[int]) -> dict[int, int]:
    if not mids:
        return {}
    return dict(db.execute(select(RSVP.meetup_id, func.count()).where(
        RSVP.meetup_id.in_(mids), RSVP.cancelled.is_(False)).group_by(RSVP.meetup_id)).all())


_UNSET = object()


def _meetup_view(db: Session, m: Meetup, lang: str, sid: str | None = None, going: int | None = None,
                 rsvp: RSVP | None | object = _UNSET) -> dict:
    host = db.get(Daai, m.host_id)
    if going is None:
        going = _going_counts(db, [m.id]).get(m.id, 0)
    r = rsvp
    if r is _UNSET:
        r = db.scalars(select(RSVP).where(RSVP.meetup_id == m.id, RSVP.session_id == sid,
                                          RSVP.cancelled.is_(False))).first() if sid else None
    mine = {"code": r.code, "nickname": r.nickname} if r else None
    return {"id": m.id, "title": m.title, "description": m.description, "lang": m.lang, "country": m.country,
            "city": m.city, "venue": m.venue, "starts_at": iso(m.starts_at), "duration_min": m.duration_min,
            "capacity": m.capacity, "going": going, "spots_left": max(0, m.capacity - going), "audience": m.audience,
            "host": host.public(_ui(lang)) if host else None, "group_id": m.group_id, "status": m.status,
            "is_demo": m.is_demo, "my_rsvp": mine}


@router.get("/meetups")
def list_meetups(country: str = "", city: str = "", lang: str = "", ui: str = "ar",
                 me: SeekerSession | None = Depends(optional_seeker), db: Session = Depends(get_db)):
    q = select(Meetup).where(Meetup.status == "open", Meetup.starts_at >= utcnow() - timedelta(hours=3))
    if country:
        q = q.where(Meetup.country == country)
    if city:
        q = q.where(Meetup.city == city)
    if lang:
        q = q.where(Meetup.lang == lang)
    meetups = db.scalars(q.order_by(Meetup.starts_at)).all()
    mids = [m.id for m in meetups]
    going = _going_counts(db, mids)
    mine: dict[int, RSVP] = {}
    if me and mids:
        mine = {r.meetup_id: r for r in db.scalars(select(RSVP).where(
            RSVP.session_id == me.id, RSVP.cancelled.is_(False), RSVP.meetup_id.in_(mids))).all()}
    return [_meetup_view(db, m, ui, going=going.get(m.id, 0), rsvp=mine.get(m.id)) for m in meetups]


class RsvpIn(BaseModel):
    nickname: str = Field(min_length=2, max_length=40)
    confirm_audience: bool = False


@router.post("/meetups/{mid}/rsvp")
def rsvp(mid: int, body: RsvpIn, ui: str = "ar", me: SeekerSession = Depends(seeker),
         db: Session = Depends(get_db)):
    m = db.get(Meetup, mid)
    if not m or m.status != "open":
        raise HTTPException(404, "not found")
    if m.audience in ("women", "men") and not body.confirm_audience:
        raise HTTPException(400, "please confirm the audience of this meetup")
    existing = db.scalars(select(RSVP).where(RSVP.meetup_id == mid, RSVP.session_id == me.id,
                                             RSVP.cancelled.is_(False))).first()
    if existing:
        return _meetup_view(db, m, ui, me.id)
    if m.starts_at <= utcnow():
        raise HTTPException(409, "meetup already started")
    going = _going_counts(db, [mid]).get(mid, 0)
    if going >= m.capacity:
        raise HTTPException(409, "full")
    nick = moderation.clean_nickname(body.nickname)
    if not moderation.nickname_ok(nick):
        raise HTTPException(400, "choose another nickname")
    db.add(RSVP(meetup_id=mid, session_id=me.id, nickname=nick, code=booking_code()))
    db.commit()
    return _meetup_view(db, m, ui, me.id)


@router.post("/meetups/{mid}/cancel-rsvp")
def cancel_rsvp(mid: int, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    r = db.scalars(select(RSVP).where(RSVP.meetup_id == mid, RSVP.session_id == me.id, RSVP.cancelled.is_(False))).first()
    if r:
        r.cancelled = True
        db.commit()
    return {"ok": True}


def _ics_time(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _ics_text(s: str) -> str:
    """RFC 5545 TEXT escaping. A bare CR would otherwise start a new property line."""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def _ics_fold(line: str) -> str:
    """Folds a content line at 75 octets without splitting a UTF-8 character (Arabic is 2 bytes a letter)."""
    out, cur, size = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > 75:
            out.append(cur)
            cur, size = " ", 1
        cur += ch
        size += n
    out.append(cur)
    return "\r\n".join(out)


@router.get("/meetups/{mid}/ics")
def meetup_ics(mid: int, db: Session = Depends(get_db)):
    m = db.get(Meetup, mid)
    if not m:
        raise HTTPException(404, "not found")

    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Sabeeli//Meetups//AR", "BEGIN:VEVENT",
        f"UID:sabeeli-meetup-{m.id}@sabeeli", f"DTSTAMP:{_ics_time(utcnow())}",
        f"DTSTART:{_ics_time(m.starts_at)}", f"DTEND:{_ics_time(m.starts_at + timedelta(minutes=m.duration_min))}",
        f"SUMMARY:{_ics_text(m.title)}", f"LOCATION:{_ics_text(m.venue + ', ' + m.city)}",
        f"DESCRIPTION:{_ics_text(m.description)}",
        f"STATUS:{'CANCELLED' if m.status == 'cancelled' else 'CONFIRMED'}",
        "END:VEVENT", "END:VCALENDAR"]
    body = "".join(_ics_fold(line) + "\r\n" for line in lines)
    return Response(body, media_type="text/calendar",
                    headers={"Content-Disposition": f'attachment; filename="sabeeli-meetup-{m.id}.ics"'})


class MeetupIn(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(default="", max_length=2000)
    lang: str = Field(default="ar", pattern=LANG)
    country: str = Field(default="", max_length=64)
    city: str = Field(min_length=2, max_length=64)
    venue: str = Field(min_length=3, max_length=200)
    starts_at: datetime
    duration_min: int = Field(default=90, ge=15, le=480)
    capacity: int = Field(default=20, ge=2, le=500)
    audience: str = "all"
    group_id: int | None = None
    public_venue: bool = False


@router.get("/daai/meetups")
def my_meetups(ui: str = "ar", lead: Daai = Depends(daai), db: Session = Depends(get_db)):
    meetups = db.scalars(select(Meetup).where(Meetup.host_id == lead.id).order_by(Meetup.starts_at)).all()
    attendees: dict[int, list[str]] = {m.id: [] for m in meetups}
    if meetups:
        for r in db.scalars(select(RSVP).where(RSVP.meetup_id.in_(list(attendees)), RSVP.cancelled.is_(False))
                            .order_by(RSVP.id)).all():
            attendees[r.meetup_id].append(r.nickname)
    return [{**_meetup_view(db, m, ui, going=len(attendees[m.id]), rsvp=None), "attendees": attendees[m.id]}
            for m in meetups]


@router.post("/daai/meetups")
def create_meetup(body: MeetupIn, ui: str = "ar", lead: Daai = Depends(daai), db: Session = Depends(get_db)):
    if not body.public_venue:
        raise HTTPException(400, "meetups must be at a public venue")
    if body.audience not in ("all", "women", "men", "families"):
        raise HTTPException(400, "bad audience")
    starts = body.starts_at if body.starts_at.tzinfo is None else \
        body.starts_at.astimezone(timezone.utc).replace(tzinfo=None)
    if starts <= utcnow():
        raise HTTPException(400, "the meetup must start in the future")
    if body.group_id:
        g = db.get(Group, body.group_id)
        if not g or g.leader_id != lead.id:
            raise HTTPException(400, "you can only link your own group")
    m = Meetup(title=body.title.strip(), description=body.description.strip(), lang=body.lang, country=body.country,
               city=body.city.strip(), venue=body.venue.strip(), starts_at=starts, duration_min=body.duration_min,
               capacity=body.capacity, audience=body.audience, host_id=lead.id, group_id=body.group_id)
    db.add(m)
    db.commit()
    return _meetup_view(db, m, ui)


@router.post("/daai/meetups/{mid}/cancel")
def cancel_meetup(mid: int, lead: Daai = Depends(daai), db: Session = Depends(get_db)):
    m = db.get(Meetup, mid)
    if not m or m.host_id != lead.id:
        raise HTTPException(404, "not found")
    m.status = "cancelled"
    db.commit()
    return {"ok": True}
