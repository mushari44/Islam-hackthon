"""Checks every group message goes through before it is posted. Owner: Mushari.

Order: length -> rate limit -> abuse (blocked, counts a strike; 3 strikes mutes)
-> personal details and links (redacted, the message still posts).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ...core.textnorm import normalize_ar

MAX_LEN = 1000
MIN_SECONDS_BETWEEN_POSTS = 3
STRIKES_TO_MUTE = 3

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
URL = re.compile(r"(https?://\S+|www\.\S+|\b[\w-]+\.(com|net|org|io|me|sa|co|info)\b\S*)", re.I)
PHONE = re.compile(r"(?<!\d)(\+?\d[\d\s\-()]{7,}\d)")
HANDLE = re.compile(r"(?<![\w@])@(?!سبيلي|sabeeli)[A-Za-z0-9_.]{3,}", re.I)

# A short, deliberately conservative list; extend it with the reviewers' list.
ABUSE = [
    "كلب", "حمار", "غبي", "حقير", "تافه", "لعنة الله عليك", "يلعن",
    "idiot", "stupid", "moron", "fuck", "shit", "bitch", "bastard", "terrorist religion",
]
_ABUSE_RE = re.compile("|".join(rf"(?<!\w){re.escape(normalize_ar(w))}(?!\w)" for w in ABUSE), re.I)


@dataclass
class Verdict:
    ok: bool
    text: str
    reason: str = ""        # "", too_long, too_fast, abuse, empty
    redacted: bool = False


def check(text: str, seconds_since_last: float | None) -> Verdict:
    text = (text or "").strip()
    if not text:
        return Verdict(False, "", "empty")
    if len(text) > MAX_LEN:
        return Verdict(False, text, "too_long")
    if seconds_since_last is not None and seconds_since_last < MIN_SECONDS_BETWEEN_POSTS:
        return Verdict(False, text, "too_fast")
    if _ABUSE_RE.search(normalize_ar(text)):
        return Verdict(False, text, "abuse")
    cleaned = EMAIL.sub("[…]", text)
    cleaned = URL.sub("[…]", cleaned)
    cleaned = PHONE.sub("[…]", cleaned)
    cleaned = HANDLE.sub("[…]", cleaned)
    return Verdict(True, cleaned, "", redacted=cleaned != text)


BOT_MENTION = re.compile(r"@\s?(سبيلي|سَبِيلي|sabeeli)\b", re.I)


def mentions_bot(text: str) -> bool:
    return bool(BOT_MENTION.search(text or ""))


def strip_mention(text: str) -> str:
    return BOT_MENTION.sub("", text or "").strip(" ،,:")


def clean_nickname(nick: str) -> str:
    nick = re.sub(r"\s+", " ", (nick or "").strip())[:24]
    nick = EMAIL.sub("", PHONE.sub("", URL.sub("", nick))).strip()
    return nick
