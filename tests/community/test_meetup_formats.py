"""Online and in-person meetups, the attendee-only meeting link, "My activities", and demo meetups that stay
upcoming and keep their venue's local time."""
from datetime import timedelta

from sqlalchemy import select

from backend.app.core.db import SessionLocal, utcnow
from backend.app.features.community import seed as community_seed
from backend.app.features.community.models import Meetup

LINK = "https://meet.example.com/test-circle"


def new_device(client):
    return {"X-Seeker": client.post("/api/session").json()["token"]}


def online_meetup(client, lead, **extra):
    body = {"title": "حلقة عن بعد للاختبار", "format": "online", "online_url": LINK, "starts_at": "2030-03-01T18:00:00Z",
            "tz": "Asia/Riyadh", **extra}
    res = client.post("/api/daai/meetups", json=body, headers=lead)
    assert res.status_code == 200, res.text
    return res.json()


def test_online_meetup_rules(client, daai_login):
    lead = daai_login("khalid")
    made = online_meetup(client, lead, city="الرياض", venue="بيتي", country="SA")
    # no place for an online meetup, and the host sees the link
    assert (made["format"], made["city"], made["venue"], made["country"]) == ("online", "", "", "")
    assert made["online_url"] == LINK and made["tz"] == "Asia/Riyadh"

    base = {"title": "لقاء", "starts_at": "2030-03-01T18:00:00Z"}
    for bad in ("", "http://meet.example.com/x", "javascript:alert(1)", "https://"):
        res = client.post("/api/daai/meetups", json={**base, "format": "online", "online_url": bad}, headers=lead)
        assert res.status_code == 400, bad
    assert client.post("/api/daai/meetups", json={**base, "format": "hybrid"}, headers=lead).status_code == 400
    # in person still needs a public venue, a city and a venue
    assert client.post("/api/daai/meetups", json={**base, "public_venue": True}, headers=lead).status_code == 400
    assert client.post("/api/daai/meetups", json={**base, "public_venue": False, "city": "الرياض", "venue": "مكتبة عامة"},
                       headers=lead).status_code == 400
    assert client.post("/api/daai/meetups", json={**base, "tz": "not a zone!"}, headers=lead).status_code == 422


def test_the_link_reaches_only_people_who_booked(client, daai_login):
    lead = daai_login("khalid")
    made = online_meetup(client, lead)
    listed = next(m for m in client.get("/api/meetups?format=online").json() if m["id"] == made["id"])
    assert listed["online_url"] == ""                                   # never in the public list

    h = new_device(client)
    booked = client.post(f"/api/meetups/{made['id']}/rsvp", json={"nickname": "زائر"}, headers=h).json()
    assert booked["online_url"] == LINK
    assert next(m for m in client.get("/api/meetups?format=online", headers=h).json() if m["id"] == made["id"])["online_url"] == LINK
    other = new_device(client)
    assert next(m for m in client.get("/api/meetups?format=online", headers=other).json() if m["id"] == made["id"])["online_url"] == ""

    ics = client.get(f"/api/meetups/{made['id']}/ics").text
    assert LINK not in ics and "LOCATION:" in ics                       # the calendar file is public


def test_format_and_place_filters(client, daai_login):
    lead = daai_login("khalid")
    made = online_meetup(client, lead)
    in_person = client.get("/api/meetups?format=in_person").json()
    assert in_person and all(m["format"] == "in_person" for m in in_person)
    assert all(m["format"] == "online" for m in client.get("/api/meetups?format=online").json())
    # an online meetup can be joined from any country, so a place filter keeps it
    assert made["id"] in {m["id"] for m in client.get("/api/meetups?country=GB&city=London").json()}


def test_my_activities(client, daai_login):
    lead = daai_login("maryam")
    h = new_device(client)
    later = online_meetup(client, lead, title="لقاء لاحق", starts_at="2030-05-01T18:00:00Z")
    sooner = online_meetup(client, lead, title="لقاء أقرب", starts_at="2030-04-01T18:00:00Z")
    dropped = online_meetup(client, lead, title="لقاء ألغيت حجزه", starts_at="2030-04-15T18:00:00Z")
    for m in (later, sooner, dropped):
        client.post(f"/api/meetups/{m['id']}/rsvp", json={"nickname": "زائر"}, headers=h)
    client.post(f"/api/meetups/{dropped['id']}/cancel-rsvp", json={}, headers=h)
    client.post(f"/api/daai/meetups/{later['id']}/cancel", json={}, headers=lead)     # the host cancels one
    gid = client.get("/api/groups").json()[0]["id"]
    client.post(f"/api/groups/{gid}/join", json={"nickname": "زائر", "accept_rules": True, "confirm_audience": True}, headers=h)

    mine = client.get("/api/community/mine", headers=h).json()
    assert [(m["id"], m["status"]) for m in mine["meetups"]] == [(sooner["id"], "open"), (later["id"], "cancelled")]
    assert all(m["my_rsvp"] and m["online_url"] == LINK for m in mine["meetups"])
    assert [g["id"] for g in mine["groups"]] == [gid] and mine["groups"][0]["membership"]
    assert client.get("/api/community/mine", headers=new_device(client)).json() == {"meetups": [], "groups": []}


def test_demo_meetups_stay_upcoming_in_local_time():
    db = SessionLocal()
    try:
        demo = {m.title: m for m in db.scalars(select(Meetup).where(Meetup.is_demo.is_(True))).all()}
        assert {"online"} <= {m.format for m in demo.values()} and all(m.tz for m in demo.values())
        assert all(m.online_url == "" for m in demo.values() if m.format == "in_person")
        # 18:00 in New York is 22:00 or 23:00 UTC, not 15:00 (the old seed put every city on Riyadh time)
        assert demo["Ask a Muslim: open evening"].starts_at.hour in (22, 23)

        # a database seeded before time zones existed, and a demo meetup that has passed
        old, past = demo["لقاء تعريفي: من هو محمد ﷺ؟"], demo["Open evening: Questions about Islam"]
        old.tz, old.starts_at = "", utcnow() - timedelta(days=40)
        past.starts_at = utcnow() - timedelta(days=9, hours=2)
        hour = community_seed._shift(past.starts_at, "GB", to_utc=False).hour
        db.commit()
        community_seed.seed(db, {})          # demo data exists: only the refresh runs
        db.refresh(old)
        db.refresh(past)
        assert old.tz == "Asia/Riyadh" and old.starts_at > utcnow()
        assert utcnow() < past.starts_at < utcnow() + timedelta(days=7)
        assert community_seed._shift(past.starts_at, "GB", to_utc=False).hour == hour   # same local hour
    finally:
        db.close()
