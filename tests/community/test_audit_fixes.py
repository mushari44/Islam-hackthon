"""Fixes from the overnight audit (4 October): simultaneous bookings, contact details hidden with invisible
characters, and the demo meetup linked to another da'i's group. Owner: Mushari."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.app.core.db import SessionLocal
from backend.app.features.community import moderation
from backend.app.features.community.models import RSVP
from tests.community.test_meetup_formats import new_device, online_meetup


@pytest.mark.parametrize("text", ["اتصل 0​5​5​1​2​3​4​5​6​7",
                                  "evil​.com", "@​myhandle123", "055.123.4567"])
def test_contact_details_with_invisible_characters_are_redacted(text):
    v = moderation.check(text, None)
    assert v.ok and v.redacted and "​" not in v.text


def test_simultaneous_bookings_respect_capacity_and_one_per_seeker(client, daai_login):
    made = online_meetup(client, daai_login("khalid"), capacity=2, registration="required")
    url = f"/api/meetups/{made['id']}/rsvp"
    devices = [new_device(client) for _ in range(6)]
    with ThreadPoolExecutor(6) as ex:
        codes = list(ex.map(lambda h: client.post(url, json={"nickname": "زائر"}, headers=h).status_code, devices))
    assert codes.count(200) == 2 and codes.count(409) == 4

    other = online_meetup(client, daai_login("khalid"))
    h = new_device(client)
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(lambda _: client.post(f"/api/meetups/{other['id']}/rsvp", json={"nickname": "زائر"}, headers=h),
                    range(4)))
    db = SessionLocal()
    try:
        assert db.query(RSVP).filter(RSVP.meetup_id == other["id"], RSVP.cancelled.is_(False)).count() == 1
    finally:
        db.close()
    client.post(f"/api/meetups/{other['id']}/cancel-rsvp", headers=h)
    listed = next(m for m in client.get("/api/meetups?format=online", headers=h).json() if m["id"] == other["id"])
    assert listed["online_url"] == "" and not listed.get("my_rsvp")


def test_demo_meetups_link_only_their_hosts_groups(client):
    db = SessionLocal()
    try:
        from backend.app.features.community.models import Group, Meetup
        for m in db.query(Meetup).filter(Meetup.group_id.isnot(None)).all():
            assert db.get(Group, m.group_id).leader_id == m.host_id, m.title
    finally:
        db.close()
