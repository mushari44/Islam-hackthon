"""The sample da'is, groups and meetups show no "demo" tag (Mushari, 6 October 2026), and a database seeded with the
old tags loses them on the next start, without touching what a da'i edited."""
from sqlalchemy import select

from backend.app.core.db import SessionLocal
from backend.app.features.auth.models import Daai
from backend.app.features.auth.seed import seed_accounts
from backend.app.features.community import seed as community_seed
from backend.app.features.community.models import Group, GroupMessage, Meetup

TAGS = ("تجريبي", "تجريبية", "demo")


def tagged(text: str) -> bool:
    return any(tag in text.lower() for tag in TAGS)


def test_sample_data_has_no_demo_tags(client):
    db = SessionLocal()
    try:
        meetups = db.scalars(select(Meetup).where(Meetup.is_demo.is_(True))).all()
        assert meetups and not any(tagged(f"{m.description} {m.venue} {m.online_url}") for m in meetups)
        daais = db.scalars(select(Daai).where(Daai.is_demo.is_(True))).all()
        assert daais and not any(tagged(f"{d.display_name} {d.display_name_en} {d.bio} {d.bio_en}") for d in daais)
        welcomes = db.scalars(select(GroupMessage).join(Group, Group.id == GroupMessage.group_id)
                              .where(Group.is_demo.is_(True), GroupMessage.author_type == "daai")).all()
        assert welcomes and not any(tagged(w.author_name) for w in welcomes)
    finally:
        db.close()

    names = {p["name"] for p in client.get("/api/daais?lang=en&ui=ar").json()}
    assert "خالد" in names and not any(tagged(n) for n in names)


def test_old_demo_tags_are_removed_on_start(client):
    db = SessionLocal()
    try:
        khalid = db.scalars(select(Daai).where(Daai.username == "khalid")).one()
        maryam = db.scalars(select(Daai).where(Daai.username == "maryam")).one()
        meetup = db.scalars(select(Meetup).where(Meetup.title == "لقاء تعريفي: من هو محمد ﷺ؟")).one()
        online = db.scalars(select(Meetup).where(Meetup.is_demo.is_(True), Meetup.format == "online")).first()
        welcome = db.scalars(select(GroupMessage).where(GroupMessage.daai_id == khalid.id)).first()
        description, venue, link = meetup.description, meetup.venue, online.online_url

        # what a database seeded before 6 October holds, plus a bio Maryam wrote herself
        khalid.display_name, khalid.bio_en = "خالد (حساب تجريبي)", "Demo da'i who speaks Arabic and English."
        maryam_bio, maryam.bio = maryam.bio, "أحب الإجابة عن أسئلة الطلاب (تجريبي)"
        meetup.description, meetup.venue = f"{description} (بيانات تجريبية)", f"{venue} (مكان تجريبي)"
        online.online_url = link.replace("sabeeli-", "sabeeli-demo-")
        welcome.author_name = "خالد (حساب تجريبي)"
        db.commit()

        community_seed.seed(db, seed_accounts(db))
        for row in (khalid, maryam, meetup, online, welcome):
            db.refresh(row)
        assert (khalid.display_name, khalid.bio_en) == ("خالد", "A da'i who speaks Arabic and English.")
        assert maryam.bio == "أحب الإجابة عن أسئلة الطلاب (تجريبي)"     # her own words stay
        assert (meetup.description, meetup.venue, online.online_url) == (description, venue, link)
        assert welcome.author_name == "خالد"

        maryam.bio = maryam_bio
        db.commit()
    finally:
        db.close()
