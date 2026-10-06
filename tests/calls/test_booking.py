"""Booked calls: da'i weekly hours, free slots, booking, cancelling, joining and no-shows. Owner: Eman."""
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.features.calls import booking

ABOUT = {"gender": "f", "age_band": "25_34"}
_n = [0]


def account(client):
    """Headers for a fresh signed-in seeker account."""
    _n[0] += 1
    h = {"X-Seeker": client.post("/api/session").json()["token"]}
    res = client.post("/api/account/signup", json={"username": f"booker_{_n[0]}", "password": "long-pass-1", **ABOUT}, headers=h)
    assert res.status_code == 200
    return h


def daai_id(client, headers):
    return client.get("/api/daai/me", headers=headers).json()["id"]


def at(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)


@pytest.fixture()
def clock(monkeypatch):
    """Moves the booking rules' clock: clock(dt) makes utcnow() return dt."""
    def set_now(dt):
        monkeypatch.setattr(booking, "utcnow", lambda: dt)
    return set_now


def slots(client, **q):
    q.setdefault("lang", "ar")
    return client.get("/api/booking/slots", params=q).json()["slots"]


def test_only_signed_in_seekers_book_and_a_slot_is_taken_once(client, daai_login):
    yid = daai_id(client, daai_login("yusuf"))
    free = slots(client, lang="en", daai_id=yid)
    assert free, "demo da'is come with weekly hours"
    first = free[0]["starts_at"]
    assert at(first) >= datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=2) - timedelta(minutes=1)
    assert at(free[-1]["starts_at"]) <= datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=14, minutes=1)

    anon = {"X-Seeker": client.post("/api/session").json()["token"]}
    body = {"starts_at": first, "lang": "en", "daai_id": yid}
    assert client.post("/api/bookings", json=body, headers=anon).status_code == 403

    a, b = account(client), account(client)
    made = client.post("/api/bookings", json={**body, "note": "About prayer times"}, headers=a)
    assert made.status_code == 200 and made.json()["status"] == "booked" and made.json()["daai"]["id"] == yid
    assert client.post("/api/bookings", json=body, headers=b).status_code == 409          # double booking
    assert first not in [s["starts_at"] for s in slots(client, lang="en", daai_id=yid)]

    # the da'i sees the time, language and topic, never who booked
    upcoming = client.get("/api/daai/bookings", headers=daai_login("yusuf")).json()["upcoming"]
    mine = next(x for x in upcoming if x["id"] == made.json()["id"])
    assert mine["note"] == "About prayer times" and "session_id" not in mine and "seeker" not in mine


def test_sixty_minutes_needs_two_free_halves_and_cancel_gives_them_back(client, daai_login):
    yid = daai_id(client, daai_login("yusuf"))
    thirty = {s["starts_at"] for s in slots(client, lang="en", daai_id=yid)}
    sixty = [s["starts_at"] for s in slots(client, lang="en", daai_id=yid, minutes=60)]
    assert sixty and set(sixty) < thirty          # the last half hour of each range can't start an hour
    h = account(client)
    made = client.post("/api/bookings", json={"starts_at": sixty[0], "minutes": 60, "lang": "en", "daai_id": yid}, headers=h).json()
    nxt = (at(sixty[0]) + timedelta(minutes=30)).isoformat() + "Z"
    left = {s["starts_at"] for s in slots(client, lang="en", daai_id=yid)}
    assert sixty[0] not in left and nxt not in left

    assert client.post(f"/api/bookings/{made['id']}/cancel", headers=h).json()["status"] == "cancelled"
    left = {s["starts_at"] for s in slots(client, lang="en", daai_id=yid)}
    assert sixty[0] in left and nxt in left


def test_limits_three_upcoming_and_no_overlap(client):
    h = account(client)
    free = slots(client, lang="ar", gender="m")
    made = client.post("/api/bookings", json={"starts_at": free[0]["starts_at"], "lang": "ar", "gender_pref": "m"}, headers=h)
    assert made.status_code == 200 and made.json()["daai"]["gender"] == "m"
    # the same time again, even with another da'i, overlaps their own booking
    assert client.post("/api/bookings", json={"starts_at": free[0]["starts_at"], "lang": "ar"}, headers=h).status_code == 409
    for s in free[3:5]:
        assert client.post("/api/bookings", json={"starts_at": s["starts_at"], "lang": "ar"}, headers=h).status_code == 200
    res = client.post("/api/bookings", json={"starts_at": free[8]["starts_at"], "lang": "ar"}, headers=h)
    assert res.status_code == 409 and res.json()["detail"] == "too many bookings"
    assert len(client.get("/api/bookings", headers=h).json()["upcoming"]) == 3


def test_schedule_rules_pause_and_days_off(client, daai_login):
    m = daai_login("maryam")
    assert client.post("/api/daai/schedule", json={"tz": "Mars/Base", "weekly": {}}, headers=m).status_code == 400
    assert client.post("/api/daai/schedule", json={"weekly": {"sun": [["18:15", "19:00"]]}}, headers=m).status_code == 400
    assert client.post("/api/daai/schedule", json={"weekly": {"sun": [["18:00", "20:00"], ["19:00", "21:00"]]}},
                       headers=m).status_code == 400
    weekly = {d: [["00:00", "24:00"]] for d in booking.DAYS}
    saved = client.post("/api/daai/schedule", json={"tz": "Europe/London", "weekly": weekly}, headers=m).json()
    assert saved["tz"] == "Europe/London" and saved["weekly"]["mon"] == [["00:00", "24:00"]]
    mid = daai_id(client, m)
    free = slots(client, daai_id=mid)
    assert len(free) > 14 * 40                  # whole days, every half hour
    day = at(free[60]["starts_at"]).date().isoformat()   # London and UTC dates match well inside a day
    client.post("/api/daai/schedule", json={"tz": "Europe/London", "weekly": weekly, "days_off": [day]}, headers=m)
    assert all(at(s["starts_at"]).date().isoformat() != day or at(s["starts_at"]).hour == 23 for s in slots(client, daai_id=mid))
    client.post("/api/daai/schedule", json={"tz": "Europe/London", "weekly": weekly, "paused": True}, headers=m)
    assert slots(client, daai_id=mid) == []
    assert next(p for p in client.get("/api/daais?lang=ar").json() if p["id"] == mid)["bookable"] is False
    client.post("/api/daai/schedule", json={"tz": "Asia/Riyadh", "weekly": booking.DEMO_WEEKLY}, headers=m)


def test_join_start_talk_and_done(client, daai_login, clock):
    khalid = daai_login("khalid")
    kid = daai_id(client, khalid)
    h = account(client)
    start = slots(client, daai_id=kid)[0]["starts_at"]
    b = client.post("/api/bookings", json={"starts_at": start, "lang": "ar", "daai_id": kid}, headers=h).json()
    assert b["can_join"] is False and b["can_cancel"] is True

    clock(at(start) - timedelta(minutes=20))
    assert client.post(f"/api/bookings/{b['id']}/join", headers=h).status_code == 409
    assert client.post(f"/api/daai/bookings/{b['id']}/start", headers=khalid).status_code == 409
    # within 15 minutes, the da'i's general queue is held back for the booked call
    anon = account(client)
    general = client.post("/api/calls", json={"lang": "ar"}, headers=anon).json()
    clock(at(start) - timedelta(minutes=10))
    req = client.get("/api/daai/requests", headers=khalid).json()
    assert [x["id"] for x in req["booked"]] == [b["id"]] and all(x["id"] != general["id"] for x in req["waiting"])
    client.post(f"/api/calls/{general['id']}/cancel", headers=anon)

    clock(at(start) - timedelta(minutes=4))
    joined = client.post(f"/api/bookings/{b['id']}/join", headers=h).json()
    assert joined["ready"] is True and joined["call_id"] is None
    assert client.get("/api/daai/bookings", headers=khalid).json()["upcoming"][0]["seeker_waiting"] is True
    cid = client.post(f"/api/daai/bookings/{b['id']}/start", headers=khalid).json()["call_id"]
    assert client.get(f"/api/bookings/{b['id']}", headers=h).json()["call_id"] == cid
    assert client.get(f"/api/calls/{cid}", headers=h).json()["status"] == "accepted"
    assert client.post(f"/api/bookings/{b['id']}/cancel", headers=h).status_code == 409   # the call is on

    client.post(f"/api/daai/calls/{cid}/end", json={}, headers=khalid)
    assert client.get(f"/api/bookings/{b['id']}", headers=h).json()["status"] == "done"


def test_missed_by_the_daai_or_the_seeker(client, daai_login, clock):
    khalid = daai_login("khalid")
    kid = daai_id(client, khalid)
    h = account(client)
    free = slots(client, daai_id=kid)
    one = client.post("/api/bookings", json={"starts_at": free[0]["starts_at"], "lang": "ar", "daai_id": kid}, headers=h).json()
    two = client.post("/api/bookings", json={"starts_at": free[4]["starts_at"], "lang": "ar", "daai_id": kid}, headers=h).json()

    three = client.post("/api/bookings", json={"starts_at": free[8]["starts_at"], "lang": "ar", "daai_id": kid}, headers=h).json()
    clock(at(three["starts_at"]) + timedelta(minutes=11))     # nobody came
    assert client.get(f"/api/bookings/{three['id']}", headers=h).json()["missed_by"] == "both"

    clock(at(one["starts_at"]) + timedelta(minutes=1))
    client.post(f"/api/bookings/{one['id']}/join", headers=h)
    clock(at(one["starts_at"]) + timedelta(minutes=11))
    missed = client.get(f"/api/bookings/{one['id']}", headers=h).json()
    assert missed["status"] == "missed" and missed["missed_by"] == "daai"

    clock(at(two["starts_at"]))
    cid = client.post(f"/api/daai/bookings/{two['id']}/start", headers=khalid).json()["call_id"]
    assert client.post(f"/api/daai/bookings/{two['id']}/no-show", headers=khalid).status_code == 409   # too early
    clock(at(two["starts_at"]) + timedelta(minutes=12))
    gone = client.post(f"/api/daai/bookings/{two['id']}/no-show", headers=khalid).json()
    assert gone["status"] == "missed" and gone["missed_by"] == "seeker"
    assert client.get(f"/api/calls/{cid}", headers=h).json()["status"] == "ended"


def test_daai_cancels_with_a_note(client, daai_login):
    yusuf = daai_login("yusuf")
    yid = daai_id(client, yusuf)
    h = account(client)
    b = client.post("/api/bookings", json={"starts_at": slots(client, lang="en", daai_id=yid)[-1]["starts_at"], "lang": "en",
                                           "daai_id": yid}, headers=h).json()
    client.post(f"/api/daai/bookings/{b['id']}/cancel", json={"note": "Travelling that day, sorry"}, headers=yusuf)
    seen = client.get("/api/bookings", headers=h).json()["past"][0]
    assert seen["status"] == "cancelled" and seen["cancelled_by"] == "daai" and seen["cancel_note"] == "Travelling that day, sorry"


def test_reschedule_moves_the_booking_and_can_extend_it(client, daai_login):
    yusuf = daai_login("yusuf")
    yid = daai_id(client, yusuf)
    h = account(client)
    sixty = [s["starts_at"] for s in slots(client, lang="en", daai_id=yid, minutes=60)]
    start = sixty[1]
    b = client.post("/api/bookings", json={"starts_at": start, "lang": "en", "daai_id": yid, "note": "Wudu"}, headers=h).json()
    # extend the same time from 30 to 60 minutes: the old half hour counts as free for the move
    moved = client.post("/api/bookings", json={"starts_at": start, "minutes": 60, "lang": "en", "daai_id": yid,
                                               "replaces": b["id"]}, headers=h)
    assert moved.status_code == 200 and moved.json()["minutes"] == 60 and moved.json()["note"] == "Wudu"
    old = client.get(f"/api/bookings/{b['id']}", headers=h).json()
    assert old["status"] == "cancelled" and old["rescheduled_to"] == moved.json()["id"]
    assert len(client.get("/api/bookings", headers=h).json()["upcoming"]) == 1
    past = client.get("/api/daai/bookings", headers=yusuf).json()["past"]
    assert next(x for x in past if x["id"] == b["id"])["rescheduled"] is True
    # a failed move keeps the old booking as it was
    other = account(client)
    taken = client.post("/api/bookings", json={"starts_at": sixty[-1], "lang": "en", "daai_id": yid}, headers=other).json()
    bad = client.post("/api/bookings", json={"starts_at": taken["starts_at"], "lang": "en", "daai_id": yid,
                                             "replaces": moved.json()["id"]}, headers=h)
    assert bad.status_code == 409
    assert client.get(f"/api/bookings/{moved.json()['id']}", headers=h).json()["status"] == "booked"
    left = {s["starts_at"] for s in slots(client, lang="en", daai_id=yid)}
    assert start not in left
