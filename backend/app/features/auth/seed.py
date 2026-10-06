"""Synthetic sample accounts so judges can try the da'i side. Nothing here is a real person. Owner: Eman.

Password: DEMO_PASSWORD (see .env.example). Set your own before deploying.
"""
from __future__ import annotations

import os

from sqlalchemy.orm import Session

from .models import Daai
from .routes import create_daai
from .security import hash_password, verify_password

DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "123")

DEMO_DAAIS = [
    {"username": "khalid", "display_name": "خالد", "display_name_en": "Khalid", "gender": "m",
     "languages": ["ar", "en"], "bio": "داعية يتحدث العربية والإنجليزية.",
     "bio_en": "A da'i who speaks Arabic and English."},
    {"username": "maryam", "display_name": "مريم", "display_name_en": "Maryam", "gender": "f",
     "languages": ["ar", "en"], "bio": "داعية تتحدث العربية والإنجليزية.",
     "bio_en": "A da'iyah who speaks Arabic and English."},
    {"username": "yusuf", "display_name": "يوسف", "display_name_en": "Yusuf", "gender": "m",
     "languages": ["en"], "bio": "داعية يتحدث الإنجليزية.",
     "bio_en": "A da'i who speaks English."},
    {"username": "reviewer", "display_name": "المراجع", "display_name_en": "Reviewer",
     "gender": "m", "languages": ["ar", "en"], "role": "admin", "bio": "حساب المراجعة وقياس جودة الإحالة.",
     "bio_en": "Review account; runs the referral comparison."},
]

# What older databases hold for these accounts: the site no longer shows a "demo" tag (Mushari, 6 October 2026),
# so a value still equal to the old seed is updated on start. A value the da'i has edited since is left alone.
_OLD_SEED = {
    "khalid": {"display_name": "خالد (حساب تجريبي)", "display_name_en": "Khalid (demo)",
               "bio": "داعية تجريبي يتحدث العربية والإنجليزية.", "bio_en": "Demo da'i who speaks Arabic and English."},
    "maryam": {"display_name": "مريم (حساب تجريبي)", "display_name_en": "Maryam (demo)",
               "bio": "داعية تجريبية تتحدث العربية والإنجليزية.", "bio_en": "Demo da'iyah who speaks Arabic and English."},
    "yusuf": {"display_name": "يوسف (حساب تجريبي)", "display_name_en": "Yusuf (demo)",
              "bio": "داعية تجريبي يتحدث الإنجليزية.", "bio_en": "Demo da'i who speaks English."},
    "reviewer": {"display_name": "المراجع (حساب تجريبي)", "display_name_en": "Reviewer (demo)",
                 "bio": "حساب المراجعة والتجارب.", "bio_en": "Review and experiment account."},
}


def seed_accounts(db: Session) -> dict[str, Daai]:
    out = {}
    for spec in DEMO_DAAIS:
        user = db.query(Daai).filter(Daai.username == spec["username"]).first()
        if not user:
            user = create_daai(db, password=DEMO_PASSWORD, is_demo=True, **spec)
        elif user.is_demo:
            # Sample accounts always use the current DEMO_PASSWORD (mushari, 6 October 2026), also in older databases.
            if not verify_password(DEMO_PASSWORD, user.password_hash):
                user.password_hash = hash_password(DEMO_PASSWORD)
            for field, old in _OLD_SEED[spec["username"]].items():
                if getattr(user, field) == old:
                    setattr(user, field, spec[field])
        out[spec["username"]] = user
    db.commit()
    return out
