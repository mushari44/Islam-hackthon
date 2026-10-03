"""Community filters by sex and age: a woman or a man sees what they can join (their own and mixed), an age
group sees its own and all-ages, and groups take an age group but never a children's one."""
from sqlalchemy import select

from backend.app.core.db import SessionLocal
from backend.app.features.community import seed as community_seed
from backend.app.features.community.models import Group


def ids(rows):
    return {r["id"] for r in rows}


def test_groups_filter_by_audience_and_age(client, daai_login):
    lead = daai_login("maryam")
    base = {"title": "مجموعة لاختبار التصفية", "lang": "ar", "country": "SA", "city": "تبوك"}
    women_youth = client.post("/api/daai/groups", json={**base, "audience": "women", "age_group": "youth"}, headers=lead).json()
    men_adults = client.post("/api/daai/groups", json={**base, "audience": "men", "age_group": "adults"}, headers=lead).json()
    mixed = client.post("/api/daai/groups", json=base, headers=lead).json()
    assert (women_youth["age_group"], men_adults["age_group"], mixed["age_group"]) == ("youth", "adults", "all")

    q = "/api/groups?country=SA&city=تبوك"
    assert ids(client.get(q).json()) == {women_youth["id"], men_adults["id"], mixed["id"]}
    assert ids(client.get(f"{q}&audience=women").json()) == {women_youth["id"], mixed["id"]}
    assert ids(client.get(f"{q}&audience=men").json()) == {men_adults["id"], mixed["id"]}
    assert ids(client.get(f"{q}&age=youth").json()) == {women_youth["id"], mixed["id"]}
    assert ids(client.get(f"{q}&audience=men&age=youth").json()) == {mixed["id"]}
    assert ids(client.get(f"{q}&audience=anyone").json()) == ids(client.get(q).json())   # unknown value: no filter

    # no children's groups online, and nothing outside the list
    for bad in ("kids", "teens"):
        assert client.post("/api/daai/groups", json={**base, "age_group": bad}, headers=lead).status_code == 400


def test_meetups_filter_by_audience(client, daai_login):
    lead = daai_login("khalid")
    base = {"title": "لقاء لاختبار التصفية", "city": "تبوك", "venue": "مكتبة عامة", "starts_at": "2030-02-01T18:00:00Z",
            "public_venue": True}
    made = {a: client.post("/api/daai/meetups", json={**base, "audience": a}, headers=lead).json()["id"]
            for a in ("all", "women", "men", "families")}
    q = "/api/meetups?city=تبوك&format=in_person"
    assert ids(client.get(q).json()) == set(made.values())
    assert ids(client.get(f"{q}&audience=women").json()) == {made["all"], made["women"], made["families"]}
    assert ids(client.get(f"{q}&audience=men").json()) == {made["all"], made["men"], made["families"]}


def test_demo_groups_get_their_age_group():
    db = SessionLocal()
    try:
        g = db.scalars(select(Group).where(Group.is_demo.is_(True), Group.title == "حلقة القاهرة: خطوة بخطوة")).one()
        assert g.age_group == "youth"
        g.age_group = "all"              # as in a database seeded before groups had an age group
        db.commit()
        community_seed.seed(db, {})      # the demo data exists, so only the backfill runs
        db.refresh(g)
        assert g.age_group == "youth"
    finally:
        db.close()
