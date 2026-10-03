"""Synthetic demo groups and meetups (labelled as demo data). Owner: Mushari."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ...core.db import utcnow
from ..auth.public import Daai
from .models import RSVP, Group, GroupMessage, Meetup

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
     "age_group": "youth",
     "description": "Support for new Muslims: prayer, wudu, the basics of faith, and a place to ask without hesitation.",
     "welcome": "Welcome to the circle! Let's start with how to pray. Tag @sabeeli for a sourced explanation."},
    {"leader": "khalid", "title": "حلقة دبي: أسئلة عن الإسلام", "lang": "ar", "country": "AE", "city": "دبي",
     "age_group": "adults",
     "description": "حلقة أسبوعية للمقيمين والزوار في دبي، نجيب فيها عن أسئلة الإسلام بهدوء ومن المصادر.",
     "welcome": "أهلاً بكم في حلقة دبي. موضوعنا هذا الأسبوع: الصلاة ومعناها. اكتبوا @سبيلي لجواب موثق."},
    {"leader": "khalid", "title": "حلقة القاهرة: خطوة بخطوة", "lang": "ar", "country": "EG", "city": "القاهرة",
     "age_group": "youth",
     "description": "تعرّف على أركان الإسلام والإيمان في حلقة ودية يقودها داعية.",
     "welcome": "مرحباً بكم. نبدأ بأركان الإيمان الستة، وكل سؤال مرحب به."},
    {"leader": "yusuf", "title": "New York circle: Islam basics", "lang": "en", "country": "US", "city": "New York",
     "description": "A weekly circle in New York for anyone curious about Islam. Questions welcome, no pressure.",
     "welcome": "Welcome! This week: who is Prophet Muhammad ﷺ? Tag @sabeeli for a sourced answer."},
    {"leader": "maryam", "title": "Kuala Lumpur sisters' circle", "lang": "en", "country": "MY", "city": "Kuala Lumpur",
     "audience": "women", "description": "A circle for women learning about Islam in Kuala Lumpur, led by a da'iyah.",
     "welcome": "Welcome, sisters! We start with the five pillars. Ask anything."},
    {"leader": "khalid", "title": "حلقة مكة المكرمة للزوار والمقيمين", "lang": "ar", "country": "SA", "city": "مكة المكرمة",
     "description": "أسئلة الزوار والمقيمين الجدد عن الإسلام، بإشراف داعية.",
     "welcome": "مرحباً بكم في مكة المكرمة. اسألوا عمّا يثير فضولكم، واكتبوا @سبيلي لجواب موثق."},
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
    # "Word and deed in Islam" series: each meetup pairs a short lesson with something done together.
    {"host": "khalid", "group": 0, "title": "القول والعمل (١): الصدق في الكلام والوفاء بالوعد", "lang": "ar",
     "country": "SA", "city": "الرياض", "venue": "ساحة المركز الثقافي (مكان تجريبي)", "days": 8, "hour": 19,
     "capacity": 60, "audience": "all", "registration": "open", "series": "qawl_amal",
     "description": "درس قصير عن الصدق والوفاء، ثم نشاط جماعي نطبّق فيه ما تعلمناه. الدخول حر دون تسجيل. (بيانات تجريبية)"},
    {"host": "yusuf", "group": 1, "title": "Word and Deed (2): Kindness to neighbours", "lang": "en", "country": "GB",
     "city": "London", "venue": "Community centre garden (demo venue)", "days": 10, "hour": 10, "capacity": 20,
     "audience": "all", "age_group": "youth", "series": "qawl_amal",
     "description": "A short talk on kindness to neighbours, then a volunteering morning packing food parcels. (demo data)"},
    {"host": "maryam", "group": 2, "title": "قصص الأنبياء للأطفال مع أهاليهم", "lang": "ar", "country": "SA", "city": "جدة",
     "venue": "مكتبة الطفل العامة (مكان تجريبي)", "days": 14, "hour": 16, "capacity": 20, "audience": "families",
     "age_group": "kids", "description": "حكايات ونشاط رسم للأطفال، ويحضر كل طفل مع ولي أمره. (بيانات تجريبية)"},
    {"host": "khalid", "group": 4, "title": "زيارة مفتوحة لمسجد في دبي", "lang": "ar", "country": "AE", "city": "دبي",
     "venue": "مركز ثقافي عام بجوار المسجد (مكان تجريبي)", "days": 7, "hour": 17, "capacity": 40, "audience": "all",
     "registration": "open", "description": "جولة تعريفية بالمسجد وآدابه، وأسئلة مفتوحة مع داعية. (بيانات تجريبية)"},
    {"host": "khalid", "group": 5, "title": "القول والعمل (٣): إطعام الطعام", "lang": "ar", "country": "EG", "city": "القاهرة",
     "venue": "ساحة مركز شباب عام (مكان تجريبي)", "days": 11, "hour": 16, "capacity": 30, "audience": "all",
     "age_group": "youth", "series": "qawl_amal",
     "description": "درس قصير عن فضل إطعام الطعام، ثم نجهز معاً وجبات للمحتاجين. (بيانات تجريبية)"},
    {"host": "yusuf", "group": 6, "title": "Ask a Muslim: open evening", "lang": "en", "country": "US", "city": "New York",
     "venue": "Public library meeting room (demo venue)", "days": 13, "hour": 18, "capacity": 35, "audience": "all",
     "age_group": "adults", "description": "An open conversation with a guide for curious adults. (demo data)"},
    {"host": "khalid", "title": "القول والعمل (٤): حفظ اللسان", "lang": "ar", "country": "SA", "city": "أبها",
     "venue": "قاعة المكتبة العامة (مكان تجريبي)", "days": 15, "hour": 19, "capacity": 25, "audience": "men",
     "age_group": "youth", "series": "qawl_amal",
     "description": "درس قصير عن حفظ اللسان، ثم تحدٍّ جماعي لأسبوع نتابع فيه بعضنا. (بيانات تجريبية)"},
    {"host": "maryam", "title": "لقاء تعريفي للزائرات في الدمام", "lang": "ar", "country": "SA", "city": "الدمام",
     "venue": "مركز ثقافي عام (مكان تجريبي)", "days": 9, "hour": 17, "capacity": 20, "audience": "women",
     "registration": "open", "description": "جلسة ودية للتعارف والأسئلة عن الإسلام. (بيانات تجريبية)"},
    # Online meetups: the link (a placeholder for the demo) is shown only to people who join. `zone` sets the hour.
    {"host": "khalid", "group": 0, "title": "حلقة عن بُعد: أسئلة المهتمين بالإسلام", "lang": "ar", "format": "online",
     "online_url": "https://meet.example.com/sabeeli-demo-ar", "zone": "SA", "days": 5, "hour": 20, "capacity": 50,
     "audience": "all", "registration": "open",
     "description": "لقاء مباشر عبر الإنترنت: اسأل عن الإسلام من بيتك مع داعية. يظهر رابط اللقاء لمن ينضم. (بيانات تجريبية)"},
    {"host": "yusuf", "group": 1, "title": "Online circle: Questions about Islam", "lang": "en", "format": "online",
     "online_url": "https://meet.example.com/sabeeli-demo-en", "zone": "GB", "days": 6, "hour": 19, "capacity": 40,
     "audience": "all",
     "description": "A live video circle with a guide: ask anything about Islam from home. Book a place to get the link. (demo data)"},
    {"host": "maryam", "group": 2, "title": "لقاء نسائي عن بُعد: أسئلة المسلمات الجدد", "lang": "ar", "format": "online",
     "online_url": "https://meet.example.com/sabeeli-demo-women", "zone": "SA", "days": 8, "hour": 21, "capacity": 25,
     "audience": "women",
     "description": "لقاء مرئي للنساء مع داعية للإجابة عن أسئلة المسلمات الجدد والمهتمات. (بيانات تجريبية)"},
    # Ramadan 1448 (expected mid-February to mid-March 2027). Times are in UTC.
    {"host": "khalid", "group": 0, "title": "إفطار جماعي: تعرّف على رمضان", "lang": "ar", "country": "SA", "city": "الرياض",
     "venue": "ساحة المركز الثقافي (مكان تجريبي)", "at": (2027, 2, 12, 14, 30), "capacity": 120, "audience": "all",
     "registration": "open", "series": "ramadan",
     "description": "نفطر معاً ونتعرف على معنى الصيام وعادات رمضان. الكل مرحب به. (بيانات تجريبية)"},
    {"host": "khalid", "title": "ليلة تعريفية بصلاة التراويح", "lang": "ar", "country": "SA",
     "city": "المدينة المنورة", "venue": "قاعة عامة قرب المسجد (مكان تجريبي)", "at": (2027, 2, 15, 17, 30),
     "capacity": 40, "audience": "all", "series": "ramadan",
     "description": "شرح مبسط لصلاة التراويح وقيام رمضان، ثم نشهدها معاً. (بيانات تجريبية)"},
    {"host": "maryam", "title": "إفطار عائلي مع الجيران", "lang": "ar", "country": "SA", "city": "جدة",
     "venue": "حديقة عامة (مكان تجريبي)", "at": (2027, 2, 20, 14, 45), "capacity": 60, "audience": "families",
     "series": "ramadan", "description": "إفطار للعائلات ونشاط للأطفال عن قيم رمضان. (بيانات تجريبية)"},
    {"host": "yusuf", "group": 2, "title": "Open iftar: Ramadan with neighbours", "lang": "en", "country": "GB",
     "city": "London", "venue": "Community centre hall (demo venue)", "at": (2027, 2, 18, 17, 30), "capacity": 80,
     "audience": "all", "registration": "open", "series": "ramadan",
     "description": "Break the fast with us and ask anything about Ramadan. Everyone welcome. (demo data)"},
]


# Each demo venue's zone, with its summer offset as a fallback for a machine without time zone data (tzdata is in
# requirements.txt, so the fallback is only for an older install).
ZONES = {"SA": ("Asia/Riyadh", 3), "AE": ("Asia/Dubai", 4), "EG": ("Africa/Cairo", 3), "GB": ("Europe/London", 1),
         "US": ("America/New_York", -4), "MY": ("Asia/Kuala_Lumpur", 8)}


def _zone(spec: dict) -> str:
    return spec.get("zone") or spec["country"]


def _shift(dt: datetime, code: str, to_utc: bool) -> datetime:
    """Converts a naive time between UTC and local time in the zone of country `code`."""
    name, offset = ZONES[code]
    try:
        zone = ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return dt - timedelta(hours=offset) if to_utc else dt + timedelta(hours=offset)
    if to_utc:
        return dt.replace(tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
    return dt.replace(tzinfo=timezone.utc).astimezone(zone).replace(tzinfo=None)


def _start(spec: dict) -> datetime:
    """`at` is a fixed UTC time; otherwise `days` from today at `hour` o'clock, local time at the venue."""
    if "at" in spec:
        return datetime(*spec["at"])
    code = _zone(spec)
    today = _shift(utcnow(), code, to_utc=False).replace(hour=0, minute=0, second=0, microsecond=0)
    return _shift(today + timedelta(days=spec["days"], hours=spec["hour"]), code, to_utc=True)


def _meetup(spec: dict, daais: dict[str, Daai], groups: list[Group]) -> Meetup:
    online = spec.get("format") == "online"
    group = groups[spec["group"]] if "group" in spec and spec["group"] < len(groups) else None
    return Meetup(title=spec["title"], description=spec["description"], lang=spec["lang"],
                  country="" if online else spec["country"], city="" if online else spec["city"],
                  venue="" if online else spec["venue"], capacity=spec["capacity"], audience=spec["audience"],
                  registration=spec.get("registration", "required"), age_group=spec.get("age_group", "all"),
                  series=spec.get("series", ""), format=spec.get("format", "in_person"),
                  online_url=spec.get("online_url", ""), tz=ZONES[_zone(spec)][0], starts_at=_start(spec),
                  host_id=daais[spec["host"]].id, group_id=group.id if group else None, is_demo=True)


def seed(db: Session, daais: dict[str, Daai]) -> None:
    if db.scalars(select(Group).where(Group.is_demo.is_(True))).first():
        _backfill_age_groups(db)
        _refresh_demo_meetups(db, daais)
        return
    groups = []
    for spec in GROUPS:
        leader = daais[spec["leader"]]
        g = Group(title=spec["title"], description=spec["description"], lang=spec["lang"], country=spec["country"],
                  city=spec["city"], audience=spec.get("audience", "all"), age_group=spec.get("age_group", "all"),
                  leader_id=leader.id, is_demo=True)
        db.add(g)
        db.flush()
        db.add(GroupMessage(group_id=g.id, author_type="daai", author_name=leader.display_name if spec["lang"] == "ar"
                            else leader.display_name_en, daai_id=leader.id, text=spec["welcome"]))
        groups.append(g)
    for spec in MEETUPS:
        db.add(_meetup(spec, daais, groups))
    db.commit()


def _refresh_demo_meetups(db: Session, daais: dict[str, Daai]) -> None:
    """Keeps an older or long-running demo database in step: adds demo meetups added to MEETUPS since, gives older
    ones their time zone (keeping their date but moving them to the venue's local hour: the old seed put every city
    on Riyadh time), and moves relative ones that have passed forward by whole weeks with their old bookings
    cleared, so the demo always has upcoming meetups. Only demo rows are touched."""
    rows = {m.title: m for m in db.scalars(select(Meetup).where(Meetup.is_demo.is_(True))).all()}
    groups = db.scalars(select(Group).where(Group.is_demo.is_(True)).order_by(Group.id)).all()
    now = utcnow()
    for spec in MEETUPS:
        m = rows.get(spec["title"])
        if m is None:
            if spec["host"] in daais:
                db.add(_meetup(spec, daais, groups))
            continue
        if not m.tz:
            m.tz = ZONES[_zone(spec)][0]
            if "days" in spec:   # keep the date people saw (the old seed's Riyadh date), at the venue's local hour
                day = (m.starts_at + timedelta(hours=3)).replace(hour=0, minute=0, second=0, microsecond=0)
                m.starts_at = _shift(day + timedelta(hours=spec["hour"]), _zone(spec), to_utc=True)
        if "days" in spec and m.status == "open" and m.starts_at < now - timedelta(hours=3):
            code, weeks = _zone(spec), (now - m.starts_at).days // 7 + 1
            m.starts_at = _shift(_shift(m.starts_at, code, to_utc=False) + timedelta(weeks=weeks), code, to_utc=True)
            db.execute(delete(RSVP).where(RSVP.meetup_id == m.id))   # a new date starts with no bookings
    db.commit()


def _backfill_age_groups(db: Session) -> None:
    """Demo groups seeded before groups had an age group get the one their spec gives now."""
    ages = {spec["title"]: spec["age_group"] for spec in GROUPS if "age_group" in spec}
    rows = db.scalars(select(Group).where(Group.is_demo.is_(True), Group.title.in_(ages), Group.age_group == "all")).all()
    for g in rows:
        g.age_group = ages[g.title]
    if rows:
        db.commit()
