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
    open_all = next(m for m in meetups if m["audience"] == "all" and m["registration"] == "required"
                    and m["age_group"] == "all")
    res = client.post(f"/api/meetups/{open_all['id']}/rsvp", json={"nickname": "زائر"}, headers=h).json()
    assert len(res["my_rsvp"]["code"]) == 8
    assert "BEGIN:VCALENDAR" in client.get(f"/api/meetups/{open_all['id']}/ics").text
    women = next(m for m in meetups if m["audience"] == "women")
    assert client.post(f"/api/meetups/{women['id']}/rsvp", json={"nickname": "زائرة"}, headers=h).status_code == 400


def test_meetups_need_public_venue(client, daai_login):
    lead = daai_login("khalid")
    body = {"title": "لقاء", "city": "الرياض", "venue": "بيتي", "starts_at": "2030-01-01T15:00:00Z", "public_venue": False}
    assert client.post("/api/daai/meetups", json=body, headers=lead).status_code == 400


def test_meetup_types_and_filters(client, seeker):
    h = seeker_headers(seeker)
    walk_in = client.get("/api/meetups?registration=open").json()
    assert walk_in and all(m["registration"] == "open" for m in walk_in)
    # a walk-in event is joined with one tap (no capacity limit)
    joinable = next(m for m in walk_in if m["audience"] == "all" and m["age_group"] == "all")
    joined = client.post(f"/api/meetups/{joinable['id']}/rsvp", json={"nickname": "زائر"}, headers=h)
    assert joined.status_code == 200 and joined.json()["my_rsvp"]
    series = client.get("/api/meetups?series=qawl_amal").json()
    assert len(series) >= 2 and all(m["series"] == "qawl_amal" for m in series)
    youth = client.get("/api/meetups?age=youth").json()
    assert youth and all(m["age_group"] in ("youth", "all") for m in youth)
    # children only come with a guardian, who confirms it when booking
    kids = next(m for m in client.get("/api/meetups?age=kids").json() if m["age_group"] == "kids")
    assert client.post(f"/api/meetups/{kids['id']}/rsvp", json={"nickname": "زائرة"}, headers=h).status_code == 400
    ok = client.post(f"/api/meetups/{kids['id']}/rsvp", json={"nickname": "زائرة", "confirm_audience": True}, headers=h)
    assert ok.status_code == 200 and ok.json()["my_rsvp"]


def test_meetup_type_is_validated(client, daai_login):
    lead = daai_login("khalid")
    body = {"title": "لقاء", "city": "الرياض", "venue": "مكتبة عامة", "starts_at": "2030-01-01T18:00:00",
            "public_venue": True, "age_group": "teens"}
    assert client.post("/api/daai/meetups", json=body, headers=lead).status_code == 400
    body.update(age_group="youth", registration="open", series="qawl_amal")
    made = client.post("/api/daai/meetups", json=body, headers=lead).json()
    assert (made["registration"], made["age_group"], made["series"]) == ("open", "youth", "qawl_amal")


def test_places_and_country_filters(client):
    places = {p["country"]: p["cities"] for p in client.get("/api/community/places").json()}
    assert {"SA", "GB", "AE", "EG", "US", "MY"} <= set(places)
    assert next(iter(places)) == "SA"                      # Saudi Arabia comes first
    assert {"الرياض", "جدة", "مكة المكرمة", "المدينة المنورة", "الدمام", "أبها"} <= set(places["SA"])
    ramadan = client.get("/api/meetups?series=ramadan").json()
    assert len(ramadan) >= 4 and all(m["series"] == "ramadan" for m in ramadan)
    assert "دبي" in places["AE"]
    dubai = client.get("/api/groups?country=AE&city=دبي").json()
    assert dubai and all(g["country"] == "AE" and g["city"] == "دبي" for g in dubai)
    cairo = client.get("/api/meetups?country=EG").json()
    assert cairo and all(m["country"] == "EG" for m in cairo)


def test_daai_can_create_a_group(client, daai_login):
    lead = daai_login("maryam")
    body = {"title": "حلقة تجريبية", "description": "", "lang": "ar", "country": "SA", "city": "جدة", "audience": "women"}
    made = client.post("/api/daai/groups", json=body, headers=lead)
    assert made.status_code == 200 and made.json()["country"] == "SA"
