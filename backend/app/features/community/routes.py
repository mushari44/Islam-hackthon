"""Community API: groups led by da'is (with the @سبيلي assistant) and in-person meetups. Owner: Mushari.

Safety rules built in: no direct messages between seekers, nicknames only,
every message moderated, the leader can delete posts and mute members,
meetups only at public venues, RSVPs collect a nickname and nothing else.

Contract used by frontend/src/features/community (see docs/API.md).
"""
from __future__ import annotations

import logging
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import available_timezones

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ...core.db import SessionLocal, get_db, iso, utcnow
from ..auth.public import Daai, SeekerSession, account_gender, daai, optional_daai, optional_seeker, seeker
from ..rag.public import answer_in_group
from . import moderation
from .models import RSVP, Group, GroupMember, GroupMessage, Meetup, NewMuslim
from .public import expire_pending, remove_new_muslim

router = APIRouter(prefix="/api")
log = logging.getLogger("sabeeli.community")
# Check-then-write steps (meetup capacity, one booking per seeker, unique nicknames, the posting rate limit)
# run under this lock, so two simultaneous requests can't both pass the check. The app runs as one process;
# several workers would need database constraints instead.
_write_lock = threading.Lock()

BOT_NAME = {"ar": "سَبِيلي (مساعد آلي)", "en": "Sabeeli (AI assistant)"}
# Posted when the assistant fails, so the asker isn't left waiting and the leader is asked to step in.
BOT_FAILED = {"ar": "تعذّر على المساعد الإجابة الآن. نبّهنا قائد المجموعة ليجيب عن سؤالك.",
              "en": "The assistant couldn't answer right now. We've asked the group leader to reply."}


LANG = r"^[a-z]{2,3}$"    # interface or content language code, e.g. ar, en, fr
TZ = re.compile(r"^[A-Za-z]+(?:/[A-Za-z0-9_+\-]+){0,2}$")    # the shape of an IANA time zone name, e.g. Asia/Riyadh
ZONES = available_timezones()         # empty when the machine has no time zone database (then only the shape is checked)
ONLINE_URL = re.compile(r"^https://[^\s<>\"'\\]{4,490}$", re.IGNORECASE)
ONLINE_LOCATION = {"ar": "عن بُعد (أونلاين)", "en": "Online"}
ONLINE_NOTE = {"ar": "رابط اللقاء في سَبِيلي: المجتمع ← أنشطتي.", "en": "The meeting link is in Sabeeli: Community > My activities."}
MESSAGES_PAGE = 200


def _zone(name: str) -> str:
    """The venue's IANA time zone, or "" when it isn't a real one. Only used to show local times, so an unknown
    zone never blocks creating a meetup."""
    name = name.strip()
    if ZONES:
        return name if name in ZONES else ""
    return name if TZ.match(name) else ""


def _meeting_link(url: str) -> str:
    """An https meeting link with nothing hidden in it (no control or text-direction characters), or ""."""
    url = url.strip()
    if not ONLINE_URL.match(url) or not url.isprintable():
        return ""
    return "https://" + url[len("https://"):]


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
            "city": g.city, "audience": g.audience, "age_group": g.age_group, "active": g.active,
            "members": _member_count(db, g.id) if members is None else members,
            "leader": leader.public(_ui(lang)) if leader else None, "is_demo": g.is_demo,
            "membership": {"id": me.id, "nickname": me.nickname, "muted": me.muted} if me else None}


def _message_view(m: GroupMessage, new_muslims: set[int] = frozenset()) -> dict:
    return {"id": m.id, "author_type": m.author_type, "author": m.author_name, "member_id": m.member_id,
            "text": "" if m.deleted else m.text, "deleted": m.deleted, "payload": {} if m.deleted else m.payload,
            "reply_to": m.reply_to, "needs_leader": m.needs_leader, "at": iso(m.created_at),
            "new_muslim": m.author_type == "seeker" and m.member_id in new_muslims}


def _new_muslim_members(db: Session, member_ids: set[int]) -> set[int]:
    """Which of these members shared that they embraced Islam (their posts carry a "new Muslim" badge)."""
    member_ids.discard(None)
    if not member_ids:
        return set()
    rows = db.execute(select(GroupMember.id).join(NewMuslim, NewMuslim.session_id == GroupMember.session_id)
                      .where(GroupMember.id.in_(member_ids), NewMuslim.status == "shared")).all()
    return {r[0] for r in rows}


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
def list_groups(lang: str = "", country: str = "", city: str = "", audience: str = "", age: str = "", ui: str = "ar",
                me: SeekerSession | None = Depends(optional_seeker), db: Session = Depends(get_db)):
    q = select(Group).where(Group.active.is_(True))
    if lang:
        q = q.where(Group.lang == lang)
    if country:
        q = q.where(Group.country == country)
    if city:
        q = q.where(Group.city == city)
    if audience in ("women", "men"):   # groups this person can join: their own and mixed ones
        q = q.where(Group.audience.in_([audience, "all"]))
    if age:
        q = q.where(Group.age_group.in_([age, "all"]))
    groups = db.scalars(q.order_by(Group.id)).all()
    counts = _member_counts(db, [g.id for g in groups])
    mine: dict[int, GroupMember] = {}
    if me and groups:
        mine = {m.group_id: m for m in db.scalars(select(GroupMember).where(
            GroupMember.session_id == me.id, GroupMember.left.is_(False),
            GroupMember.group_id.in_([g.id for g in groups]))).all()}
    return [_group_view(db, g, ui, mine.get(g.id), counts.get(g.id, 0)) for g in groups]


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
    with _write_lock:
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
    badged = _new_muslim_members(db, {m.member_id for m in msgs if m.author_type == "seeker"})
    return [_message_view(m, badged) for m in msgs]


class PostIn(BaseModel):
    text: str = Field(max_length=2000)
    lang: str = Field(default="ar", max_length=8)


@router.post("/groups/{gid}/messages")
def post_message(gid: int, body: PostIn, tasks: BackgroundTasks, me: SeekerSession = Depends(seeker),
                 db: Session = Depends(get_db)):
    g = db.get(Group, gid)
    with _write_lock:   # so simultaneous posts can't all slip past the rate limit (each @سبيلي is a model call)
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
    return {**_message_view(msg, _new_muslim_members(db, {member.id})), "redacted": verdict.redacted}


# ---------------------------------------------------------------------------
# "Became Muslim": the da'i confirms it in the call (features/calls), the seeker decides here whether their
# groups hear the news. Nothing is announced and no badge shows without the seeker's own yes.
# ---------------------------------------------------------------------------

def _welcome_text(lang: str, nick: str, gender: str) -> str:
    if lang == "ar":
        if gender == "f":
            return f"🎉 بشرى سارّة: أعلنت {nick} إسلامها. حيّاها الله في أسرتنا، ونسأل الله لها الثبات."
        return f"🎉 بشرى سارّة: أعلن {nick} إسلامه. حيّاه الله في أسرتنا، ونسأل الله له الثبات."
    return f"🎉 Good news: {nick} has embraced Islam. Welcome to the family, and may Allah keep them steadfast."


def _new_muslim_view(db: Session, row: NewMuslim | None, ui: str) -> dict:
    if row is None:
        return {"status": "none"}
    d = db.get(Daai, row.daai_id)
    groups = db.scalars(select(Group.title).join(GroupMember, GroupMember.group_id == Group.id)
                        .where(GroupMember.session_id == row.session_id, GroupMember.left.is_(False),
                               Group.active.is_(True)).order_by(Group.id)).all()
    return {"status": row.status, "daai": d.public(_ui(ui))["name"] if d else "", "groups": list(groups),
            "announced": len(row.announced or [])}


@router.get("/community/stats")
def community_stats(db: Session = Depends(get_db)):
    """Public numbers for the home page. `new_muslims` counts only people who agreed to share that they
    embraced Islam (not pending or declined confirmations), as one total with no names."""
    expire_pending(db)
    shared = db.scalar(select(func.count()).select_from(NewMuslim).where(NewMuslim.status == "shared"))
    return {"new_muslims": int(shared or 0)}


@router.get("/community/new-muslim")
def my_new_muslim(ui: str = "ar", me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    """Whether a da'i confirmed this seeker embraced Islam, and whether they shared it with their groups."""
    expire_pending(db)
    return _new_muslim_view(db, db.scalars(select(NewMuslim).where(NewMuslim.session_id == me.id)).first(), ui)


class NewMuslimIn(BaseModel):
    share: bool


@router.post("/community/new-muslim")
def answer_new_muslim(body: NewMuslimIn, ui: str = "ar", me: SeekerSession = Depends(seeker),
                      db: Session = Depends(get_db)):
    """share=true: one welcome message in each group they are in now, and the badge next to their nickname.
    share=false (also later, to take it back): the record and the welcome messages are deleted."""
    expire_pending(db)
    row = db.scalars(select(NewMuslim).where(NewMuslim.session_id == me.id)).first()
    if row is None:
        raise HTTPException(404, "nothing to answer")
    if not body.share:
        remove_new_muslim(db, me.id)
        return {"status": "none"}
    if row.status != "shared":
        gender = account_gender(db, me.id)
        with _write_lock:
            posted = []
            for member, g in db.execute(select(GroupMember, Group).join(Group, Group.id == GroupMember.group_id)
                                        .where(GroupMember.session_id == me.id, GroupMember.left.is_(False),
                                               Group.active.is_(True))).all():
                msg = GroupMessage(group_id=g.id, author_type="system", author_name="", member_id=member.id,
                                   text=_welcome_text(g.lang, member.nickname, gender), payload={"kind": "new_muslim"})
                db.add(msg)
                db.flush()
                posted.append(msg.id)
            row.status, row.answered_at, row.announced = "shared", utcnow(), posted
            db.commit()
    return _new_muslim_view(db, row, ui)


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
    age_group: str = "all"


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
    if body.age_group not in GROUP_AGE_GROUPS:
        raise HTTPException(400, "bad age group")
    g = Group(title=body.title.strip(), description=body.description.strip(), lang=body.lang,
              country=body.country.strip(), city=body.city.strip(), audience=body.audience,
              age_group=body.age_group, leader_id=lead.id)
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
                 rsvp: RSVP | None | object = _UNSET, host_view: bool = False) -> dict:
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
            "registration": m.registration, "age_group": m.age_group, "series": m.series,
            "format": m.format, "tz": m.tz,
            # the meeting link goes only to the host and people who booked (until the host cancels), never into the
            # public list
            "online_url": m.online_url if m.format == "online" and (host_view or (r and m.status != "cancelled")) else "",
            "host": host.public(_ui(lang)) if host else None, "group_id": m.group_id, "status": m.status,
            "is_demo": m.is_demo, "my_rsvp": mine}


@router.get("/meetups")
def list_meetups(country: str = "", city: str = "", lang: str = "", ui: str = "ar",
                 registration: str = "", age: str = "", series: str = "", audience: str = "", format: str = "",
                 me: SeekerSession | None = Depends(optional_seeker), db: Session = Depends(get_db)):
    q = select(Meetup).where(Meetup.status == "open", Meetup.starts_at >= utcnow() - timedelta(hours=3))
    if country:   # an online meetup can be joined from anywhere
        q = q.where(or_(Meetup.country == country, Meetup.format == "online"))
    if city:
        q = q.where(or_(Meetup.city == city, Meetup.format == "online"))
    if format in FORMATS:
        q = q.where(Meetup.format == format)
    if lang:
        q = q.where(Meetup.lang == lang)
    if registration:
        q = q.where(Meetup.registration == registration)
    if age:   # a meetup for all ages also suits every age group
        q = q.where(Meetup.age_group.in_([age, "all"]))
    if audience in ("women", "men"):   # meetups this person can attend, family events included
        q = q.where(Meetup.audience.in_([audience, "all", "families"]))
    if series:
        q = q.where(Meetup.series == series)
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
    if (m.audience in ("women", "men") or m.age_group == "kids") and not body.confirm_audience:
        raise HTTPException(400, "please confirm the audience of this meetup")
    nick = moderation.clean_nickname(body.nickname)
    with _write_lock:
        existing = db.scalars(select(RSVP).where(RSVP.meetup_id == mid, RSVP.session_id == me.id,
                                                 RSVP.cancelled.is_(False))).first()
        if existing:
            return _meetup_view(db, m, ui, me.id)
        if m.starts_at <= utcnow():
            raise HTTPException(409, "meetup already started")
        going = _going_counts(db, [mid]).get(mid, 0)
        if going >= m.capacity and m.registration == "required":   # walk-in events only count who joined
            raise HTTPException(409, "full")
        if not moderation.nickname_ok(nick):
            raise HTTPException(400, "choose another nickname")
        db.add(RSVP(meetup_id=mid, session_id=me.id, nickname=nick, code=booking_code()))
        db.commit()
    return _meetup_view(db, m, ui, me.id)


@router.post("/meetups/{mid}/cancel-rsvp")
def cancel_rsvp(mid: int, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    # Every active booking, in case an older copy made two (the lock in rsvp() now stops that).
    rows = db.scalars(select(RSVP).where(RSVP.meetup_id == mid, RSVP.session_id == me.id,
                                         RSVP.cancelled.is_(False))).all()
    for r in rows:
        r.cancelled = True
    if rows:
        db.commit()
    return {"ok": True}


@router.get("/community/mine")
def my_activities(ui: str = "ar", me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    """What this seeker takes part in: booked meetups (from 30 days ago on, soonest first, including ones the
    host cancelled, so the seeker learns of it) and the groups they are in."""
    booked = {r.meetup_id: r for r in db.scalars(select(RSVP).where(RSVP.session_id == me.id,
                                                                     RSVP.cancelled.is_(False))).all()}
    meetups = db.scalars(select(Meetup).where(Meetup.id.in_(list(booked)),
                                              Meetup.starts_at >= utcnow() - timedelta(days=30))
                         .order_by(Meetup.starts_at)).all() if booked else []
    going = _going_counts(db, [m.id for m in meetups])
    member = {m.group_id: m for m in db.scalars(select(GroupMember).where(GroupMember.session_id == me.id,
                                                                          GroupMember.left.is_(False))).all()}
    groups = db.scalars(select(Group).where(Group.id.in_(list(member)), Group.active.is_(True))
                        .order_by(Group.id)).all() if member else []
    counts = _member_counts(db, [g.id for g in groups])
    return {"meetups": [_meetup_view(db, m, ui, going=going.get(m.id, 0), rsvp=booked[m.id]) for m in meetups],
            "groups": [_group_view(db, g, ui, member[g.id], counts.get(g.id, 0)) for g in groups]}


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
    # This file is public, so an online meetup's link stays in the app: attendees find it under My activities.
    online = m.format == "online"
    where = ONLINE_LOCATION.get(m.lang, ONLINE_LOCATION["en"]) if online else f"{m.venue}, {m.city}"
    about = f"{m.description}\n\n{ONLINE_NOTE.get(m.lang, ONLINE_NOTE['en'])}".strip() if online else m.description
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Sabeeli//Meetups//AR", "BEGIN:VEVENT",
        f"UID:sabeeli-meetup-{m.id}@sabeeli", f"DTSTAMP:{_ics_time(utcnow())}",
        f"DTSTART:{_ics_time(m.starts_at)}", f"DTEND:{_ics_time(m.starts_at + timedelta(minutes=m.duration_min))}",
        f"SUMMARY:{_ics_text(m.title)}", f"LOCATION:{_ics_text(where)}", f"DESCRIPTION:{_ics_text(about)}",
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
    city: str = Field(default="", max_length=64)       # required in person (checked below)
    venue: str = Field(default="", max_length=200)     # required in person (checked below)
    starts_at: datetime
    duration_min: int = Field(default=90, ge=15, le=480)
    capacity: int = Field(default=20, ge=2, le=500)
    audience: str = "all"
    registration: str = "required"
    age_group: str = "all"
    series: str = ""
    group_id: int | None = None
    public_venue: bool = False
    format: str = "in_person"
    online_url: str = Field(default="", max_length=500)
    tz: str = Field(default="", max_length=64)          # the venue's time zone; unknown ones are stored as ""


FORMATS = ("in_person", "online")
REGISTRATION = ("required", "open")
AGE_GROUPS = ("all", "kids", "youth", "adults", "seniors")
GROUP_AGE_GROUPS = ("all", "youth", "adults", "seniors")   # an online group with strangers is no place for children
SERIES = ("", "qawl_amal", "ramadan")


@router.get("/daai/meetups")
def my_meetups(ui: str = "ar", lead: Daai = Depends(daai), db: Session = Depends(get_db)):
    meetups = db.scalars(select(Meetup).where(Meetup.host_id == lead.id).order_by(Meetup.starts_at)).all()
    attendees: dict[int, list[str]] = {m.id: [] for m in meetups}
    if meetups:
        for r in db.scalars(select(RSVP).where(RSVP.meetup_id.in_(list(attendees)), RSVP.cancelled.is_(False))
                            .order_by(RSVP.id)).all():
            attendees[r.meetup_id].append(r.nickname)
    return [{**_meetup_view(db, m, ui, going=len(attendees[m.id]), rsvp=None, host_view=True),
             "attendees": attendees[m.id]} for m in meetups]


@router.post("/daai/meetups")
def create_meetup(body: MeetupIn, ui: str = "ar", lead: Daai = Depends(daai), db: Session = Depends(get_db)):
    if body.format not in FORMATS:
        raise HTTPException(400, "bad meetup format")
    online = body.format == "online"
    url, city, venue = _meeting_link(body.online_url), body.city.strip(), body.venue.strip()
    if online and not url:
        raise HTTPException(400, "an online meetup needs an https meeting link")
    if online and body.age_group == "kids":   # children attend with a guardian at a public venue, not on a video call
        raise HTTPException(400, "a meetup for children must be in person")
    if not online:
        if not body.public_venue:
            raise HTTPException(400, "meetups must be at a public venue")
        if len(city) < 2 or len(venue) < 3:
            raise HTTPException(400, "a meetup in person needs a city and a venue")
    if body.audience not in ("all", "women", "men", "families"):
        raise HTTPException(400, "bad audience")
    if body.registration not in REGISTRATION or body.age_group not in AGE_GROUPS or body.series not in SERIES:
        raise HTTPException(400, "bad meetup type")
    starts = body.starts_at if body.starts_at.tzinfo is None else \
        body.starts_at.astimezone(timezone.utc).replace(tzinfo=None)
    if starts <= utcnow():
        raise HTTPException(400, "the meetup must start in the future")
    if body.group_id:
        g = db.get(Group, body.group_id)
        if not g or g.leader_id != lead.id:
            raise HTTPException(400, "you can only link your own group")
    m = Meetup(title=body.title.strip(), description=body.description.strip(), lang=body.lang,
               country="" if online else body.country, city="" if online else city, venue="" if online else venue,
               starts_at=starts, duration_min=body.duration_min, capacity=body.capacity, audience=body.audience,
               registration=body.registration, age_group=body.age_group, series=body.series, host_id=lead.id,
               group_id=body.group_id, format=body.format, online_url=url if online else "", tz=_zone(body.tz))
    db.add(m)
    db.commit()
    return _meetup_view(db, m, ui, host_view=True)


@router.post("/daai/meetups/{mid}/cancel")
def cancel_meetup(mid: int, lead: Daai = Depends(daai), db: Session = Depends(get_db)):
    m = db.get(Meetup, mid)
    if not m or m.host_id != lead.id:
        raise HTTPException(404, "not found")
    m.status = "cancelled"
    db.commit()
    return {"ok": True}
