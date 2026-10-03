"""Checks every group message goes through before it is posted. Owner: Mushari.

Order: length -> rate limit -> abuse (blocked, counts a strike; 3 strikes mutes)
-> personal details and links (redacted, the message still posts).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from ...core.textnorm import normalize_ar

MAX_LEN = 1000
MIN_SECONDS_BETWEEN_POSTS = 3
STRIKES_TO_MUTE = 3

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
URL = re.compile(r"(https?://\S+|www\.\S+|\b[\w-]+\.(com|net|org|io|me|sa|co|info)\b\S*)", re.I)
PHONE = re.compile(r"(?<!\d)(\+?\d[\d\s\-()]{7,}\d)")
HANDLE = re.compile(r"(?<![\w@])@(?!(?:سبيلي|سَبِيلي|sabeeli)(?![\w.]))[A-Za-z0-9_.]{3,}", re.I)
# Bidi overrides can make a message or nickname display differently from what was checked.
BIDI = re.compile("[\u202a-\u202e\u2066-\u2069]")

# A short, deliberately conservative list; extend it with the reviewers' list.
ABUSE = [
    "كلب", "حمار", "غبي", "حقير", "تافه", "لعنة الله عليك", "يلعن",
    "idiot", "stupid", "moron", "fuck", "shit", "bitch", "bastard", "terrorist religion",
]
# Arabic attaches و ف ب ل يا ال to the next word ("ياغبي", "والكلب"), and the feminine
# ending ة/ه ("غبية"), so those are allowed around an Arabic entry.
_AR_PREFIX = r"(?:و|ف|ب|ل|يا|ال|وال|يال)?"


def _abuse_pattern(word: str) -> str:
    w = re.escape(normalize_ar(word))
    if re.search(r"[\u0600-\u06ff]", word):
        return rf"(?<!\w){_AR_PREFIX}{w}(?:ه)?(?!\w)"
    return rf"(?<!\w){w}(?!\w)"


_ABUSE_RE = re.compile("|".join(_abuse_pattern(w) for w in ABUSE), re.I)

RESERVED_NICKS = ("سبيلي", "sabeeli", "admin", "moderator", "مشرف", "داعيه")


def _invisible_free(text: str) -> str:
    """Drops zero-width and other format characters, which can hide a word from the filter."""
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


@dataclass
class Verdict:
    ok: bool
    text: str
    reason: str = ""        # "", too_long, too_fast, abuse, empty
    redacted: bool = False


def check(text: str, seconds_since_last: float | None) -> Verdict:
    text = BIDI.sub("", text or "").strip()
    if not text:
        return Verdict(False, "", "empty")
    if len(text) > MAX_LEN:
        return Verdict(False, text, "too_long")
    if seconds_since_last is not None and seconds_since_last < MIN_SECONDS_BETWEEN_POSTS:
        return Verdict(False, text, "too_fast")
    if _ABUSE_RE.search(normalize_ar(_invisible_free(text))):
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
    nick = re.sub(r"\s+", " ", _invisible_free(nick or "").strip())[:24]
    nick = HANDLE.sub("", EMAIL.sub("", PHONE.sub("", URL.sub("", nick))))
    return nick.strip(" @")


def nickname_ok(nick: str) -> bool:
    """A cleaned nickname: long enough, not abusive, and not posing as the assistant or a moderator."""
    if len(nick) < 2 or not check(nick, None).ok:
        return False
    folded = normalize_ar(nick).lower()
    return not any(normalize_ar(r).lower() in folded for r in RESERVED_NICKS)
