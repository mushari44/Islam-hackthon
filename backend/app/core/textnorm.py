"""Arabic and English text normalisation shared by search, verse matching and moderation.

Code points are written with chr() so the invisible combining marks stay readable in the source.
"""
from __future__ import annotations

import re
import unicodedata


def _range(a: int, b: int) -> str:
    return f"{chr(a)}-{chr(b)}"


ARABIC_BLOCKS = _range(0x0600, 0x06FF) + _range(0x0750, 0x077F) + _range(0x08A0, 0x08FF)
ARABIC_RE = re.compile(f"[{ARABIC_BLOCKS}]")
WORD_RE = re.compile(rf"[\w{ARABIC_BLOCKS}]+", re.UNICODE)

ALEF = chr(0x0627)
ALEF_MAKSURA = chr(0x0649)
YEH = chr(0x064A)
WAW = chr(0x0648)
HAMZA = chr(0x0621)
DAGGER_ALEF = chr(0x0670)       # superscript alef: Uthmani long "a" (ٱلرَّحۡمَٰنِ)
SMALL_WAW = chr(0x06E5)
SMALL_YEH = chr(0x06E6)
SMALL_HIGH_YEH = chr(0x06E7)
TATWEEL = chr(0x0640)
HARAKAT = _range(0x064B, 0x065F) + chr(0x06E1)

_LETTER_MAP = str.maketrans({
    chr(0x0671): ALEF,          # alef wasla
    chr(0x0623): ALEF,          # alef with hamza above
    chr(0x0625): ALEF,          # alef with hamza below
    chr(0x0622): ALEF,          # alef with madda
    ALEF_MAKSURA: YEH,
    chr(0x0629): chr(0x0647),   # teh marbuta -> heh
    chr(0x0624): WAW,           # waw with hamza
    chr(0x0626): YEH,           # yeh with hamza
    chr(0x06CC): YEH,           # farsi yeh
    chr(0x06A9): chr(0x0643),   # keheh -> kaf
})

_MID_WORD_MAKSURA = re.compile(ALEF_MAKSURA + DAGGER_ALEF + f"(?=[{HARAKAT}]*[{_range(0x0621, 0x064A)}])")


def has_arabic(text: str) -> bool:
    return bool(ARABIC_RE.search(text or ""))


def strip_marks(text: str) -> str:
    """Remove harakat, Quranic annotation marks and tatweel."""
    return "".join(ch for ch in text if ch != TATWEEL and unicodedata.category(ch) != "Mn")


def normalize_ar(text: str) -> str:
    """Loose Arabic normal form used for search and spelling-independent comparison."""
    text = (text or "").replace(SMALL_WAW, "").replace(SMALL_YEH, YEH).replace(SMALL_HIGH_YEH, YEH)
    text = text.replace(WAW + DAGGER_ALEF, ALEF)                 # Uthmani صلوٰة -> صلاة
    text = _MID_WORD_MAKSURA.sub(ALEF, text)                      # أَدۡرَىٰكَ -> أدراك
    text = text.replace(ALEF_MAKSURA + DAGGER_ALEF, ALEF_MAKSURA)  # word-final مُوسَىٰ -> موسى
    text = text.replace(DAGGER_ALEF, ALEF)
    text = strip_marks(text).translate(_LETTER_MAP).replace(HAMZA, "")
    return re.sub(r"\s+", " ", text).strip()


def skeleton(text: str) -> str:
    """Alef-free, space-free letter sequence. Tolerates Uthmani vs. standard spelling."""
    norm = normalize_ar(text)
    return "".join(ch for ch in norm if ARABIC_RE.match(ch) and ch != ALEF)


# --- tokenisation for BM25 -------------------------------------------------

AR_STOP = set("""
في من على الى إلى عن ان أن إن ما لا لم لن هو هي هم هن انت أنت انا أنا نحن هذا هذه ذلك تلك الذي التي الذين
كان كانت يكون قد قال يا او أو ثم كل كما بعد قبل عند حتى اذا إذا لو بل غير بين مع منه منها له لها لهم به بها
ف و ب ك ل هل ماذا لماذا كيف متى اين أين اي أي لكن وما ومن وهو وهي وفي وعلى ايها أيها
""".split())
AR_STOP = {normalize_ar(w) for w in AR_STOP}

EN_STOP = set("""
a an the and or but if then of to in on at by for with from as is are was were be been being am do does did
this that these those it its i you he she we they me him her us them my your his our their what which who whom
why how when where can could would should will shall may might must not no yes so than too very just about into
over also there here any some all each such only own same other more most
""".split())

_AR_PREFIXES = ("وال", "فال", "بال", "كال", "لل", "ال", "و", "ف", "ب", "ك", "ل")
_AR_SUFFIXES = ("هما", "كما", "تما", "ها", "هم", "هن", "كم", "كن", "نا", "ون", "ين", "ان", "ات", "وا", "ه", "ي", "ت")


def stem_ar(token: str) -> str:
    for p in _AR_PREFIXES:
        if token.startswith(p) and len(token) - len(p) >= 3:
            token = token[len(p):]
            break
    for s in _AR_SUFFIXES:
        if token.endswith(s) and len(token) - len(s) >= 3:
            token = token[: -len(s)]
            break
    return token


def stem_en(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokens(text: str) -> list[str]:
    """Search tokens for mixed Arabic/English text."""
    out: list[str] = []
    for raw in WORD_RE.findall(text or ""):
        if has_arabic(raw):
            t = normalize_ar(raw)
            if not t or t in AR_STOP or len(t) < 2:
                continue
            out.append(stem_ar(t))
        else:
            t = raw.lower()
            if t.isdigit() or t in EN_STOP or len(t) < 2:
                continue
            out.append(stem_en(t))
    return out
