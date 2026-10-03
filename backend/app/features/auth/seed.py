"""Synthetic demo accounts so judges can try the da'i side. Nothing here is a real person. Owner: Eman.

Password: DEMO_PASSWORD (see .env.example). Set your own before deploying.
"""
from __future__ import annotations

import os

from sqlalchemy.orm import Session

from .models import Daai
from .routes import create_daai

DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "sabeeli-demo")

DEMO_DAAIS = [
    {"username": "khalid", "display_name": "خالد (حساب تجريبي)", "display_name_en": "Khalid (demo)", "gender": "m",
     "languages": ["ar", "en"], "bio": "داعية تجريبي يتحدث العربية والإنجليزية.",
     "bio_en": "Demo da'i who speaks Arabic and English."},
    {"username": "maryam", "display_name": "مريم (حساب تجريبي)", "display_name_en": "Maryam (demo)", "gender": "f",
     "languages": ["ar", "en"], "bio": "داعية تجريبية تتحدث العربية والإنجليزية.",
     "bio_en": "Demo da'iyah who speaks Arabic and English."},
    {"username": "yusuf", "display_name": "يوسف (حساب تجريبي)", "display_name_en": "Yusuf (demo)", "gender": "m",
     "languages": ["en"], "bio": "داعية تجريبي يتحدث الإنجليزية.",
     "bio_en": "Demo da'i who speaks English."},
    {"username": "reviewer", "display_name": "المراجع (حساب تجريبي)", "display_name_en": "Reviewer (demo)",
     "gender": "m", "languages": ["ar", "en"], "role": "admin", "bio": "حساب المراجعة والتجارب.",
     "bio_en": "Review and experiment account."},
]


def seed_accounts(db: Session) -> dict[str, Daai]:
    out = {}
    for spec in DEMO_DAAIS:
        user = db.query(Daai).filter(Daai.username == spec["username"]).first()
        if not user:
            user = create_daai(db, password=DEMO_PASSWORD, is_demo=True, **spec)
        out[spec["username"]] = user
    db.commit()
    return out
