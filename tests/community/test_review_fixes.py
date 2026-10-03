"""Regression tests for the community review of 3 October: moderation gaps, mute bypass, paging, meetups. Owner: Mushari."""
from datetime import timedelta

import pytest

from backend.app.core.db import SessionLocal, utcnow
from backend.app.features.community import moderation, routes
from backend.app.features.community.models import GroupMessage, Meetup
from tests.conftest import seeker_headers


def _group(client, title_lang="ar", audience="all"):
    return next(g for g in client.get(f"/api/groups?lang={title_lang}").json() if g["audience"] == audience)


def _join(client, h, gid, nick, **extra):
    return client.post(f"/api/groups/{gid}/join", json={"nickname": nick, "accept_rules": True, **extra}, headers=h)


# --- moderation ------------------------------------------------------------

@pytest.mark.parametrize("text", ["انت غ‌بي", "ياغبي", "والكلب", "انتِ غبية", "STUPID"])
def test_abuse_filter_catches_common_evasions(text):
    assert moderation.check(text, None).reason == "abuse"


@pytest.mark.parametrize("text", ["كلمة مكتوبة", "سورة البقرة", "@سبيلي ما التوحيد؟", "@sabeeli, what is salah?"])
def test_abuse_filter_leaves_normal_text(text):
    assert moderation.check(text, None).ok


def test_handles_that_start_like_the_bot_are_redacted():
    v = moderation.check("follow @sabeeli_official", None)
    assert v.redacted and "sabeeli_official" not in v.text
    assert moderation.mentions_bot("@sabeeli what is tawhid") and not moderation.mentions_bot("@sabeelix hi")


def test_bidi_overrides_are_removed():
    assert "‮" not in moderation.check("abc‮def", None).text


@pytest.mark.parametrize("nick", ["سَبِيلي (مساعد آلي)", "Sabeeli", "مشرف", "@insta_me", "a​"])
def test_nicknames_that_impersonate_or_hide_contacts_are_refused(nick):
    assert not moderation.nickname_ok(moderation.clean_nickname(nick))


# --- groups ----------------------------------------------------------------

def test_leaving_and_rejoining_keeps_a_mute(client, seeker, daai_login):
    h, lead = seeker_headers(seeker), daai_login("khalid")
    g = client.get("/api/daai/groups", headers=lead).json()[0]
    me = _join(client, h, g["id"], "متعلم").json()["membership"]
    client.post(f"/api/daai/groups/{g['id']}/members/{me['id']}/mute", json={"muted": True}, headers=lead)
    client.post(f"/api/groups/{g['id']}/leave", headers=h)
    again = _join(client, h, g["id"], "متعلم٢").json()["membership"]
    assert again["muted"] and again["id"] == me["id"]
    assert client.post(f"/api/groups/{g['id']}/messages", json={"text": "سلام", "lang": "ar"}, headers=h).status_code == 403


def test_join_uses_the_interface_language(client, seeker):
    g = _group(client, "en")
    res = client.post(f"/api/groups/{g['id']}/join?ui=en", json={"nickname": "reader", "accept_rules": True},
                      headers=seeker_headers(seeker)).json()
    ar = client.get(f"/api/groups/{g['id']}?ui=ar").json()
    assert res["leader"]["name"] != ar["leader"]["name"]


def test_women_group_needs_audience_confirmation(client, seeker):
    g = _group(client, "ar", "women")
    h = seeker_headers(seeker)
    assert _join(client, h, g["id"], "زائرة").status_code == 400
    assert _join(client, h, g["id"], "زائرة", confirm_audience=True).status_code == 200


def test_first_page_of_messages_is_the_newest(client, seeker):
    h = seeker_headers(seeker)
    g = _group(client, "ar")
    _join(client, h, g["id"], "قارئ")
    with SessionLocal() as db:
        db.add_all([GroupMessage(group_id=g["id"], author_type="seeker", author_name="x", text=f"m{i}")
                    for i in range(routes.MESSAGES_PAGE + 5)])
        db.commit()
        newest = db.query(GroupMessage).filter_by(group_id=g["id"]).order_by(GroupMessage.id.desc()).first().id
    first = client.get(f"/api/groups/{g['id']}/messages", headers=h).json()
    assert len(first) == routes.MESSAGES_PAGE and first[-1]["id"] == newest
    assert [m["id"] for m in first] == sorted(m["id"] for m in first)
    assert client.get(f"/api/groups/{g['id']}/messages?after={newest}", headers=h).json() == []


def test_leader_post_uses_the_group_language(client, daai_login):
    lead = daai_login("yusuf")
    g = next(x for x in client.get("/api/daai/groups", headers=lead).json() if x["lang"] == "en")
    msg = client.post(f"/api/daai/groups/{g['id']}/messages", json={"text": "Welcome"}, headers=lead).json()
    assert msg["author"] == client.get(f"/api/groups/{g['id']}?ui=en").json()["leader"]["name"]


def test_assistant_failure_posts_a_notice_for_the_leader(client, seeker, monkeypatch):
    def boom(question, lang):
        raise RuntimeError("model down")
    monkeypatch.setattr(routes, "answer_in_group", boom)
    h = seeker_headers(seeker)
    g = _group(client, "en")
    _join(client, h, g["id"], "asker")
    client.post(f"/api/groups/{g['id']}/messages", json={"text": "@sabeeli what is zakat?", "lang": "en"}, headers=h)
    bot = [m for m in client.get(f"/api/groups/{g['id']}/messages", headers=h).json() if m["author_type"] == "bot"]
    assert bot[-1]["needs_leader"] and bot[-1]["text"] == routes.BOT_FAILED["en"]


def test_group_fields_are_bounded(client, daai_login):
    lead = daai_login("khalid")
    assert client.post("/api/daai/groups", json={"title": "حلقة", "lang": "x" * 50}, headers=lead).status_code == 422
    assert client.post("/api/daai/groups", json={"title": "حلقة", "city": "c" * 500}, headers=lead).status_code == 422


# --- meetups ---------------------------------------------------------------

def test_rsvp_nickname_is_moderated(client, seeker):
    m = next(x for x in client.get("/api/meetups").json() if x["audience"] == "all")
    res = client.post(f"/api/meetups/{m['id']}/rsvp", json={"nickname": "غبي"}, headers=seeker_headers(seeker))
    assert res.status_code == 400


def test_no_booking_after_a_meetup_starts(client, seeker, daai_login):
    with SessionLocal() as db:
        m = db.query(Meetup).filter_by(audience="all").first()
        m2 = Meetup(title="بدأ", city=m.city, venue=m.venue, starts_at=utcnow() - timedelta(minutes=30),
                    host_id=m.host_id, capacity=10)
        db.add(m2)
        db.commit()
        mid = m2.id
    res = client.post(f"/api/meetups/{mid}/rsvp", json={"nickname": "متأخر"}, headers=seeker_headers(seeker))
    assert res.status_code == 409 and res.json()["detail"] == "meetup already started"


def test_meetup_must_be_in_the_future(client, daai_login):
    body = {"title": "لقاء", "city": "الرياض", "venue": "مكتبة عامة", "starts_at": "2020-01-01T15:00:00Z",
            "public_venue": True}
    assert client.post("/api/daai/meetups", json=body, headers=daai_login("khalid")).status_code == 400


def test_calendar_file_cannot_be_injected_and_is_folded(client, daai_login):
    lead = daai_login("khalid")
    body = {"title": "لقاء\rATTENDEE:mailto:x@example.com", "description": "وصف " * 40, "city": "الرياض",
            "venue": "مكتبة عامة", "starts_at": (utcnow() + timedelta(days=3)).isoformat() + "Z", "public_venue": True}
    m = client.post("/api/daai/meetups", json=body, headers=lead).json()
    ics = client.get(f"/api/meetups/{m['id']}/ics").text
    lines = ics.split("\r\n")
    assert not any(line.startswith("ATTENDEE") for line in lines)
    assert all(len(line.encode("utf-8")) <= 75 for line in lines)
    client.post(f"/api/daai/meetups/{m['id']}/cancel", headers=lead)
    assert "STATUS:CANCELLED" in client.get(f"/api/meetups/{m['id']}/ics").text


def test_host_list_counts_and_attendees(client, seeker, daai_login):
    lead = daai_login("yusuf")
    m = next(x for x in client.get("/api/meetups?lang=en").json() if x["audience"] == "all")
    client.post(f"/api/meetups/{m['id']}/rsvp", json={"nickname": "guest one"}, headers=seeker_headers(seeker))
    mine = next(x for x in client.get("/api/daai/meetups?ui=en", headers=lead).json() if x["id"] == m["id"])
    assert "guest one" in mine["attendees"] and mine["going"] == len(mine["attendees"]) and mine["my_rsvp"] is None
