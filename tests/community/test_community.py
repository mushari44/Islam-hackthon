"""Groups, moderation, the group assistant and meetups. Owner: Mushari."""
import time

from tests.conftest import seeker_headers


def first_group(client, lang="ar"):
    return client.get(f"/api/groups?lang={lang}").json()[0]


def test_join_post_and_moderation(client, seeker):
    h = seeker_headers(seeker)
    g = first_group(client)
    assert client.get(f"/api/groups/{g['id']}/messages", headers=h).status_code == 403   # members only
    joined = client.post(f"/api/groups/{g['id']}/join", json={"nickname": "باحث", "accept_rules": True}, headers=h).json()
    assert joined["membership"]["nickname"] == "باحث"

    posted = client.post(f"/api/groups/{g['id']}/messages", json={"text": "تواصلوا معي على test@example.com", "lang": "ar"}, headers=h).json()
    assert posted["redacted"] and "example.com" not in posted["text"]

    time.sleep(3.1)
    abuse = client.post(f"/api/groups/{g['id']}/messages", json={"text": "انت غبي", "lang": "ar"}, headers=h)
    assert abuse.status_code == 422 and abuse.json()["detail"] == "abuse"


def test_rules_must_be_accepted(client, seeker):
    g = first_group(client)
    res = client.post(f"/api/groups/{g['id']}/join", json={"nickname": "زائر", "accept_rules": False}, headers=seeker_headers(seeker))
    assert res.status_code == 400


def test_group_assistant_replies(client, seeker):
    h = seeker_headers(seeker)
    g = first_group(client, "en")
    client.post(f"/api/groups/{g['id']}/join", json={"nickname": "curious", "accept_rules": True}, headers=h)
    client.post(f"/api/groups/{g['id']}/messages", json={"text": "@sabeeli what is tawhid?", "lang": "en"}, headers=h)
    msgs = client.get(f"/api/groups/{g['id']}/messages", headers=h).json()
    bot = [m for m in msgs if m["author_type"] == "bot"]
    assert bot and bot[-1]["payload"]["segments"]


def test_leader_moderation(client, seeker, daai_login):
    h = seeker_headers(seeker)
    lead = daai_login("khalid")
    mine = client.get("/api/daai/groups", headers=lead).json()
    g = mine[0]
    client.post(f"/api/groups/{g['id']}/join", json={"nickname": "عضو", "accept_rules": True}, headers=h)
    msg = client.post(f"/api/groups/{g['id']}/messages", json={"text": "سؤال", "lang": "ar"}, headers=h).json()
    assert client.post(f"/api/daai/groups/{g['id']}/messages/{msg['id']}/delete", headers=lead).status_code == 200
    assert client.post(f"/api/daai/groups/{g['id']}/members/{msg['member_id']}/mute", json={"muted": True}, headers=lead).status_code == 200
    time.sleep(3.1)
    assert client.post(f"/api/groups/{g['id']}/messages", json={"text": "مرة أخرى", "lang": "ar"}, headers=h).status_code == 403


def test_meetup_rsvp_and_calendar(client, seeker):
    h = seeker_headers(seeker)
    meetups = client.get("/api/meetups").json()
    open_all = next(m for m in meetups if m["audience"] == "all")
    res = client.post(f"/api/meetups/{open_all['id']}/rsvp", json={"nickname": "زائر"}, headers=h).json()
    assert len(res["my_rsvp"]["code"]) == 8
    assert "BEGIN:VCALENDAR" in client.get(f"/api/meetups/{open_all['id']}/ics").text
    women = next(m for m in meetups if m["audience"] == "women")
    assert client.post(f"/api/meetups/{women['id']}/rsvp", json={"nickname": "زائرة"}, headers=h).status_code == 400


def test_meetups_need_public_venue(client, daai_login):
    lead = daai_login("khalid")
    body = {"title": "لقاء", "city": "الرياض", "venue": "بيتي", "starts_at": "2030-01-01T15:00:00Z", "public_venue": False}
    assert client.post("/api/daai/meetups", json=body, headers=lead).status_code == 400
