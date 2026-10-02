"""Synthetic demo groups and meetups (labelled as demo data). Owner: Mushari."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.db import utcnow
from ..auth.public import Daai
from .models import Group, GroupMessage, Meetup

GROUPS = [
    {"leader": "khalid", "title": "مدخل إلى الإسلام: حلقة أسبوعية", "lang": "ar", "country": "SA", "city": "الرياض",
     "description": "حلقة للتعرف على أصول الإسلام خطوة بخطوة: الإيمان بالله، والنبوة، والقرآن، والعبادات. "
                    "اسأل بحرية، ويمكنك استدعاء المساعد بكتابة @سبيلي.",
     "welcome": "مرحباً بكم في الحلقة. موضوع هذا الأسبوع: معنى التوحيد. اكتبوا أسئلتكم، ومن أراد جواباً موثقاً سريعاً فليكتب @سبيلي ثم سؤاله."},
    {"leader": "yusuf", "title": "Islam 101: weekly circle", "lang": "en", "country": "GB", "city": "London",
     "description": "A friendly circle for anyone curious about Islam. We go through the basics together and "
                    "answer questions. Mention @sabeeli for a sourced answer from the assistant.",
     "welcome": "Welcome! This week we're talking about the Quran: what it is and how Muslims understand it. "
                "Ask anything, and tag @sabeeli if you want a sourced answer right away."},
    {"leader": "maryam", "title": "حلقة المسلمات الجدد", "lang": "ar", "country": "SA", "city": "جدة", "audience": "women",
     "description": "مساحة للمسلمات الجدد والمهتمات للتعلم والسؤال في جو آمن، بإشراف داعية.",
     "welcome": "أهلاً بكنّ. نبدأ بأركان الإسلام الخمسة، وكل سؤال مرحب به."},
    {"leader": "maryam", "title": "New Muslims: first steps", "lang": "en", "country": "GB", "city": "Manchester",
     "description": "Support for new Muslims: prayer, wudu, the basics of faith, and a place to ask without hesitation.",
     "welcome": "Welcome to the circle! Let's start with how to pray. Tag @sabeeli for a sourced explanation."},
]

MEETUPS = [
    {"host": "khalid", "group": 0, "title": "لقاء تعريفي: من هو محمد ﷺ؟", "lang": "ar", "country": "SA", "city": "الرياض",
     "venue": "قاعة المكتبة العامة (مكان تجريبي)", "days": 6, "hour": 17, "capacity": 25, "audience": "all",
     "description": "لقاء مفتوح للتعرف على سيرة النبي ﷺ مع داعية، وأسئلة وأجوبة. (بيانات تجريبية)"},
    {"host": "yusuf", "group": 1, "title": "Open evening: Questions about Islam", "lang": "en", "country": "GB",
     "city": "London", "venue": "Community library hall (demo venue)", "days": 9, "hour": 18, "capacity": 30,
     "audience": "all", "description": "Bring your questions; tea and an open conversation with a guide. (demo data)"},
    {"host": "maryam", "group": 2, "title": "لقاء نسائي: الصلاة خطوة بخطوة", "lang": "ar", "country": "SA", "city": "جدة",
     "venue": "مركز ثقافي عام (مكان تجريبي)", "days": 12, "hour": 16, "capacity": 15, "audience": "women",
     "description": "لقاء عملي لتعلم الصلاة للمسلمات الجدد. (بيانات تجريبية)"},
]


def seed(db: Session, daais: dict[str, Daai]) -> None:
    if db.scalars(select(Group).where(Group.is_demo.is_(True))).first():
        return
    groups = []
    for spec in GROUPS:
        leader = daais[spec["leader"]]
        g = Group(title=spec["title"], description=spec["description"], lang=spec["lang"], country=spec["country"],
                  city=spec["city"], audience=spec.get("audience", "all"), leader_id=leader.id, is_demo=True)
        db.add(g)
        db.flush()
        db.add(GroupMessage(group_id=g.id, author_type="daai", author_name=leader.display_name if spec["lang"] == "ar"
                            else leader.display_name_en, daai_id=leader.id, text=spec["welcome"]))
        groups.append(g)
    base = utcnow().replace(minute=0, second=0, microsecond=0)
    for spec in MEETUPS:
        db.add(Meetup(title=spec["title"], description=spec["description"], lang=spec["lang"], country=spec["country"],
                      city=spec["city"], venue=spec["venue"], capacity=spec["capacity"], audience=spec["audience"],
                      starts_at=base + timedelta(days=spec["days"], hours=spec["hour"] - base.hour - 3),
                      host_id=daais[spec["host"]].id, group_id=groups[spec["group"]].id, is_demo=True))
    db.commit()
