"""Site review of 6 October: report and delete in groups, event pages, events that run long. Owner: Mushari."""
from datetime import timedelta

from backend.app.core.db import SessionLocal, utcnow
from backend.app.features.community.models import Meetup
from tests.conftest import seeker_headers, signed_in


def _member(client, gid, nick):
    h = seeker_headers(signed_in(client))
    assert client.post(f"/api/groups/{gid}/join", json={"nickname": nick, "accept_rules": True}, headers=h).status_code == 200
    return h


def _post(client, gid, h, text):
    res = client.post(f"/api/groups/{gid}/messages", json={"text": text, "lang": "ar"}, headers=h)
    assert res.status_code == 200, res.text
    return res.json()


def test_member_reports_a_message_and_the_leader_sees_it(client, daai_login):
    lead = daai_login("khalid")
    g = client.get("/api/daai/groups", headers=lead).json()[0]
    a, b = _member(client, g["id"], "كاتب1"), _member(client, g["id"], "قارئ1")
    msg = _post(client, g["id"], a, "رسالة عادية")
    assert client.post(f"/api/groups/{g['id']}/messages/{msg['id']}/report", headers=a).status_code == 400   # not your own
    for _ in range(2):   # reporting twice counts once
        assert client.post(f"/api/groups/{g['id']}/messages/{msg['id']}/report", headers=b).status_code == 200
    mine = next(x for x in client.get("/api/daai/groups", headers=lead).json() if x["id"] == g["id"])
    assert mine["needs_leader"] >= 1
    seen = next(m for m in client.get(f"/api/groups/{g['id']}/messages", headers=lead).json() if m["id"] == msg["id"])
    assert seen["reported"] and not seen["needs_leader"]   # members don't see a "waiting for the da'i" badge
    client.post(f"/api/daai/groups/{g['id']}/messages/{msg['id']}/resolve", headers=lead)
    seen = next(m for m in client.get(f"/api/groups/{g['id']}/messages", headers=lead).json() if m["id"] == msg["id"])
    assert not seen["reported"]


def test_member_deletes_only_their_own_message(client):
    g = client.get("/api/groups").json()[0]
    a, b = _member(client, g["id"], "كاتب2"), _member(client, g["id"], "قارئ2")
    msg = _post(client, g["id"], a, "سأحذفها")
    assert client.post(f"/api/groups/{g['id']}/messages/{msg['id']}/delete", headers=b).status_code == 403
    assert client.post(f"/api/groups/{g['id']}/messages/{msg['id']}/delete", headers=a).status_code == 200
    seen = next(m for m in client.get(f"/api/groups/{g['id']}/messages", headers=a).json() if m["id"] == msg["id"])
    assert seen["deleted"] and seen["text"] == ""


def test_messages_over_the_moderation_limit_are_refused_up_front(client):
    g = client.get("/api/groups").json()[0]
    a = _member(client, g["id"], "كاتب3")
    assert client.post(f"/api/groups/{g['id']}/messages", json={"text": "س" * 1001, "lang": "ar"}, headers=a).status_code == 422


def test_event_has_its_own_page(client):
    m = client.get("/api/meetups").json()[0]
    one = client.get(f"/api/meetups/{m['id']}").json()
    assert one["id"] == m["id"] and one["title"] == m["title"]
    assert client.get("/api/meetups/999999").status_code == 404


def test_long_event_stays_listed_while_it_runs_and_leaves_when_it_ends(client):
    with SessionLocal() as db:
        base = db.query(Meetup).filter(Meetup.status == "open").first()
        running = Meetup(title="long running event", description="", lang=base.lang, country=base.country, city=base.city,
                         venue=base.venue, host_id=base.host_id, starts_at=utcnow() - timedelta(hours=4), duration_min=300)
        ended = Meetup(title="ended event", description="", lang=base.lang, country=base.country, city=base.city,
                       venue=base.venue, host_id=base.host_id, starts_at=utcnow() - timedelta(hours=2), duration_min=60)
        db.add_all([running, ended])
        db.commit()
        ids = {running.id, ended.id}
    listed = {m["id"] for m in client.get("/api/meetups").json()} & ids
    assert listed == {running.id}
    with SessionLocal() as db:   # don't leave a running event for later tests to try to book
        db.query(Meetup).filter(Meetup.id.in_(ids)).update({Meetup.status: "cancelled"}, synchronize_session=False)
        db.commit()


def test_joining_posting_and_booking_need_an_account(client):
    anon = {"X-Seeker": client.post("/api/session").json()["token"]}
    g = client.get("/api/groups", headers=anon).json()[0]           # browsing stays open
    m = next(x for x in client.get("/api/meetups", headers=anon).json() if x["audience"] == "all" and x["age_group"] == "all")
    res = client.post(f"/api/groups/{g['id']}/join", json={"nickname": "زائر٣", "accept_rules": True}, headers=anon)
    assert res.status_code == 403 and res.json()["detail"] == "sign in to take part"
    assert client.post(f"/api/meetups/{m['id']}/rsvp", json={"nickname": "زائر٣"}, headers=anon).status_code == 403
    assert client.post(f"/api/groups/{g['id']}/messages", json={"text": "مرحبا", "lang": "ar"}, headers=anon).status_code == 403
