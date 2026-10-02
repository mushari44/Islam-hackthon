"""Referral cards: the summary a seeker reviews before a da'i sees it. Owner: Eman.

Three experiment arms (rotated when the experiment is on, see /api/daai/experiment):
  model    - Claude drafts the card from the conversation; the seeker edits it
  template - a fixed template: last question + the sources the answer used
  none     - no card; the da'i starts from scratch
Nothing reaches the da'i unless the seeker ticks consent.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...core.claude import LLMUnavailable, get_claude
from ...core.db import Setting, get_db
from ..auth.public import SeekerSession, seeker
from ..rag.public import conversation_transcript, last_question, source_exists
from .models import Referral

router = APIRouter(prefix="/api")

REFERRAL_SYSTEM = """You prepare a short referral card so a da'i (a human guide) can understand a seeker's question without asking them to explain it all again. The seeker will review and edit the card before deciding whether to share it.
- question: the seeker's main question in one or two sentences, in their words where possible.
- context: only background the seeker explicitly stated and that helps understand the question. Never guess or add anything about their religion, beliefs, ethnicity, health or other sensitive traits. Leave out names, phone numbers, emails, addresses and other identifying details. "" if none.
- explained: the main points the assistant already explained, each with the source ids it cited (e.g. "q:2:256", "h:2962"); [] if nothing was explained.
- unclear: what is still unclear or what the seeker wants to discuss with a person.
- language: the language the seeker prefers to talk in (e.g. "Arabic", "English").
Write the card in the seeker's language. Be brief and neutral."""

REFERRAL_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "context": {"type": "string"},
        "explained": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"point": {"type": "string"}, "sources": {"type": "array", "items": {"type": "string"}}},
                "required": ["point", "sources"],
                "additionalProperties": False,
            },
        },
        "unclear": {"type": "string"},
        "language": {"type": "string"},
    },
    "required": ["question", "context", "explained", "unclear", "language"],
    "additionalProperties": False,
}

EMPTY_CARD = {"question": "", "context": "", "explained": [], "unclear": "", "language": ""}


def next_arm(db: Session) -> str:
    row = db.get(Setting, "referral_experiment")
    cfg = dict(row.value) if row else {}
    if not cfg.get("enabled"):
        return "model"
    arms = ["model", "template", "none"]
    counter = int(cfg.get("counter", 0))
    cfg["counter"] = counter + 1
    if row:
        row.value = cfg
    else:
        db.add(Setting(key="referral_experiment", value=cfg))
    db.commit()
    return arms[counter % 3]


def template_card(db: Session, sid: str, lang: str) -> dict:
    question, sources = last_question(db, sid)
    explained = [{"point": "ما شرحه المساعد في آخر إجابة" if lang == "ar" else "What the assistant explained last",
                  "sources": sources[:6]}] if sources else []
    return {**EMPTY_CARD, "question": question, "explained": explained,
            "language": "العربية" if lang == "ar" else "English"}


def model_card(db: Session, sid: str, lang: str) -> dict:
    transcript = conversation_transcript(db, sid)
    if not transcript:
        return template_card(db, sid, lang)
    prompt = (f"Seeker's language: {'Arabic' if lang == 'ar' else 'English'}\n\n"
              f"Conversation (assistant turns list the source ids they cited):\n{transcript}")
    return get_claude().json(REFERRAL_SYSTEM, prompt, REFERRAL_SCHEMA, max_tokens=2000)


class DraftIn(BaseModel):
    lang: str = "ar"


@router.post("/referral/draft")
def draft(body: DraftIn, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    lang = "ar" if body.lang == "ar" else "en"
    arm = next_arm(db)
    mode = arm
    if arm == "model":
        try:
            card = model_card(db, me.id, lang)
        except LLMUnavailable:
            card, mode = template_card(db, me.id, lang), "template"
    elif arm == "template":
        card = template_card(db, me.id, lang)
    else:
        card = dict(EMPTY_CARD)
    for item in card.get("explained", []):
        item["sources"] = [s for s in item.get("sources", []) if source_exists(s)][:6]
    ref = Referral(session_id=me.id, mode=mode, proposed=card, final={}, lang=lang)
    db.add(ref)
    db.commit()
    return {"id": ref.id, "mode": mode, "card": card}


class ConfirmIn(BaseModel):
    consent: bool
    card: dict = Field(default_factory=dict)


def clean_card(card: dict) -> dict:
    return {
        "question": str(card.get("question", ""))[:600],
        "context": str(card.get("context", ""))[:600],
        "unclear": str(card.get("unclear", ""))[:600],
        "language": str(card.get("language", ""))[:40],
        "explained": [{"point": str(e.get("point", ""))[:300],
                       "sources": [str(s) for s in e.get("sources", []) if source_exists(str(s))][:6]}
                      for e in (card.get("explained") or [])[:6] if isinstance(e, dict)],
    }


@router.post("/referral/{rid}/confirm")
def confirm(rid: int, body: ConfirmIn, me: SeekerSession = Depends(seeker), db: Session = Depends(get_db)):
    ref = db.get(Referral, rid)
    if not ref or ref.session_id != me.id:
        raise HTTPException(404, "not found")
    final = clean_card(body.card)
    ref.consented = bool(body.consent)
    ref.final = final if body.consent else {}
    ref.edited = bool(body.consent) and final != clean_card(ref.proposed)
    db.commit()
    return {"ok": True, "consented": ref.consented}
