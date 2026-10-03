"""The question pipeline: read photo -> check quoted verses -> analyse -> retrieve -> answer -> verify.

Safety properties enforced here, not left to the prompt:
  * Scripture shown to the user is rendered from the corpus by id ([[q:..]] / [[h:..]]
    markers); Arabic verse text the model writes itself is swapped for the marker or removed.
  * Markers may only point at passages that were retrieved for this question (or at the
    Mushaf verses quoted inside a retrieved Q&A answer).
  * Personal-fatwa questions (level D) always carry the referral notice.
  * Without the model (no key, outage, refusal) the app still answers in
    sources-only mode: the closest approved passages, with no generated text.
"""
from __future__ import annotations

import logging
import math
import re
import time
from dataclasses import dataclass, field

from ...core import timing
from ...core.claude import LLMUnavailable, get_claude
from ...core.config import settings
from ...core.textnorm import has_arabic, normalize_ar, skeleton, tokens
from . import assistant, embeddings
from .assistant import AnswerResult
from .corpus import ANSWER_KINDS, Passage, get_corpus
from .quran_match import get_matcher, looks_like_quote

log = logging.getLogger("sabeeli.pipeline")
tlog = logging.getLogger("sabeeli.timing")

MARKER_RE = re.compile(r"\[\[(q:\d{1,3}:\d{1,3}|h:\d+|t:[a-z_]+|qa:\d+|b:\d+)\]\]")
QURAN_BRACKETS_RE = re.compile(r"[﴿{]([^﴾}]{3,600})[﴾}]")
QUOTE_RE = re.compile(r"[«\"“‹„]([^»\"”›“]{8,600})[»\"”›“]")
UNVERIFIED = "\uE000"     # left by the guard where a quoted text matched no source; its sentence is dropped
INTRO_MAX_WORDS = 12      # a line introducing the verse or hadith right after it («...قوله تعالى:»)
# Words that make even a short sentence a claim (a ruling, a judgement), so it must cite like any other.
CLAIM_RE = re.compile(r"(حرام|حلال|باطل|صحيح|واجب|يجب|فرض|محرم|يجوز|كفر|كافر|شرك|بدعه|حكم)"
                      r"|\b(invalid|valid|haram|halal|must|forbidden|allowed|obligatory|sinful|sin|kufr|disbeliever|ruling)\b",
                      re.I)
HARAKAT_RE = re.compile(r"[\u064B-\u0652]")

MAX_QUESTION_CHARS = 2000
# A question mark, or a word that only starts questions (not «ما»/«من», which also start verses).
INTERROGATIVE_RE = re.compile(r"[؟?]|^\s*(هل|لماذا|كيف|متى|أين|اين|ماذا|ليش|ليه|وش|شو|ايش|إيش)\b")

TEXT = {
    "greeting": {
        "ar": "وعليكم السلام ورحمة الله. أنا سَبِيلي، مساعد بالذكاء الاصطناعي يجيب عن أسئلتك حول الإسلام من مصادر معتمدة ويُظهرها لك. اسألني عمّا يثير فضولك، أو تحدّث مباشرة مع داعية بلغتك.",
        "en": "Peace be upon you. I'm Sabeeli, an AI assistant that answers questions about Islam from approved sources and shows you those sources. Ask me anything you're curious about, or talk directly with a guide (da'i) in your language.",
    },
    "thanks": {"ar": "حيّاك الله. إن كان لديك سؤال آخر فأنا هنا.", "en": "You're welcome. I'm here if you have another question."},
    "clarify_default": {"ar": "هل يمكنك توضيح سؤالك أكثر؟", "en": "Could you say a little more about what you'd like to know?"},
    "off_topic": {
        "ar": "أنا مخصص للأسئلة عن الإسلام وتعاليمه. يسعدني أن أساعدك في أي سؤال عن الإسلام.",
        "en": "I'm made for questions about Islam and its teachings. I'd be glad to help with any question about Islam.",
    },
    "request_human": {
        "ar": "يمكنك التحدث الآن مع داعية بلغتك. سأجهّز لك ملخصاً لسؤالك تراجعه وتعدّله قبل أن تقرر مشاركته.",
        "en": "You can talk with a da'i (guide) in your language now. I'll prepare a summary of your question that you can review and edit before deciding to share it.",
    },
    "abstain": {
        "ar": "لم أجد في المصادر المعتمدة المتاحة لي ما يكفي للإجابة عن هذا السؤال بثقة، ولا أريد أن أقول ما لا أستطيع إسناده. يمكنك طرحه على داعية يناقشه معك.",
        "en": "I couldn't find enough in the approved sources available to me to answer this confidently, and I don't want to say anything I can't back with a source. You can discuss it with a da'i (guide).",
    },
    "sources_only": {
        "ar": "هذه أقرب النصوص إلى سؤالك من المصادر المعتمدة. الشرح المولّد بالذكاء الاصطناعي غير متاح الآن، فأعرض النصوص كما هي من مصادرها.",
        "en": "These are the passages from the approved sources closest to your question. AI explanations are not available right now, so the texts are shown exactly as their sources publish them.",
    },
    "personal_no_model": {
        "ar": "هذا سؤال عن حالتك الشخصية، والشرح المولّد بالذكاء الاصطناعي غير متاح الآن، فلن أعرض عليك نصوصاً قد تُفهم على أنها حكم في حالتك.",
        "en": "This is a question about your own situation, and AI explanations aren't available right now, so I won't show texts that could be read as a ruling on it.",
    },
    "fatwa": {
        "ar": "سؤالك يتعلق بحالة شخصية، والحكم فيها فتوى يرجع فيها إلى عالم مؤهل أو جهة الإفتاء الرسمية في بلدك. ما سبق معلومات عامة فقط، ويمكنك التحدث مع داعية ليساعدك في معرفة من تسأل.",
        "en": "Your question is about a personal situation. A ruling on it is a fatwa, which should come from a qualified scholar or the official fatwa authority in your country. The above is general information only; a da'i can help you find whom to ask.",
    },
    "disagreement": {
        "ar": "في هذه المسألة تفصيل أو خلاف بين أهل العلم، فما ذُكر هو ما في المصادر المعتمدة المتاحة، وللتوسع يحسن سؤال مختص.",
        "en": "Scholars discuss this matter in detail and may differ on it. The above reflects the approved sources available here; for more depth, ask a specialist.",
    },
    "ocr_unavailable": {
        "ar": "قراءة النص من الصورة تحتاج خدمة الذكاء الاصطناعي، وهي غير متاحة الآن. يمكنك كتابة النص الموجود في الصورة.",
        "en": "Reading text from photos needs the AI service, which isn't available right now. You can type the text from the image instead.",
    },
    "ocr_illegible": {
        "ar": "لم أتمكن من قراءة نص واضح في الصورة. جرّب صورة أوضح أو اكتب النص.",
        "en": "I couldn't read clear text in the photo. Try a clearer photo or type the text.",
    },
    "quote_found": {
        "ar": "النص الذي أرسلته يطابق الآية في المصحف:",
        "en": "The text you sent matches this verse in the Mushaf:",
    },
    "quote_differs": {
        "ar": "النص الذي أرسلته قريب من آية، لكنه يختلف عن نص المصحف في مواضع. هذا النص الصحيح من المرجع:",
        "en": "The text you sent is close to a verse but differs from the Mushaf text in places. Here is the correct text from the reference:",
    },
    "quote_ambiguous": {
        "ar": "هذه العبارة واردة في أكثر من آية، ومنها:",
        "en": "This phrase appears in more than one verse, including:",
    },
    "quote_not_found": {
        "ar": "لم أجد هذا النص في المصحف. قد لا يكون آية، أو قد يكون منقولاً بتغيير كبير.",
        "en": "I couldn't find this text in the Mushaf. It may not be a verse, or it may be quoted with large changes.",
    },
}


def t(key: str, lang: str) -> str:
    return TEXT[key]["ar" if lang == "ar" else "en"]


# ---------------------------------------------------------------------------
# Rule-based analysis (used when the model is unavailable)
# ---------------------------------------------------------------------------

PERSONAL_AR = [r"هل يجوز (لي|ليا|لنا)", r"\b(ليا)\b", r"(يجوز|حرام|حلال)\s+(لي|علي|عليّ)", r"\bزوج(ي|تي)\b", r"\bطلاق(ي|ها)?\b",
               r"\bطلقني\b", r"\b(صلاتي|صيامي|زواجي|عقدي|وضوئي|طلاقي|ميراثي)\b", r"في حالتي", r"\bوضعي\b",
               r"\bأنا\s+(مسلم|مسلمة|امرأة|رجل|متزوج|متزوجة|أعيش|اعيش|أعمل|اعمل)", r"ماذا (أفعل|افعل)", r"\bأبي\b.*\b(يجوز|حكم)"]
PERSONAL_EN = [r"\b(can|may|should|must) i\b", r"\bam i allowed\b", r"\bis it (allowed|permissible|haram|halal|ok|okay) for me\b",
               r"\bmy (husband|wife|marriage|divorce|boss|fianc[eé]e?|boyfriend|girlfriend)\b", r"\bin my (case|situation)\b",
               r"\bi (live|work) in\b", r"\bwhat should i do\b", r"\bis it (ok|okay|fine|alright) if i\b"]
# First-person wording that is personal only next to a ruling word («أنا امرأة، هل يجوز السفر؟»,
# "I am a woman, is it allowed to travel alone?"), not in "I am a student, what is Tawhid?".
PERSONAL_WEAK = [r"\bi am\b", r"\bi'?m\b", r"\bif i\b", r"\bme\b", r"\bmy\b", r"\bانا\b", r"\bلي\b", r"\bعلي\b"]
RULING_WORD = re.compile(r"(يجوز|حرام|حلال|حكم|جائز|مباح|باطل|صحيح)|\b(allowed|permissible|haram|halal|forbidden|ruling|valid|sin)\b",
                         re.I)
# "Is X haram?", «هل الموسيقى حرام؟», «ما حكم ...»: a ruling asked for, not its wisdom ("why is pork forbidden?").
RULING_QUESTION = re.compile(
    r"^\s*(هل|ما\s+حكم|حكم)\b.*\b(حرام|حلال|يجوز|جائز|مباح|محرم|محرمة|مكروه)"
    r"|^\s*ما\s+حكم\b"
    r"|^\s*(is|are|can|may)\b.*\b(haram|halal|allowed|permissible|permitted|forbidden|prohibited|sinful)\b"
    r"|\bwhat\s+is\s+the\s+ruling\b", re.I)
DISAGREE = [r"خلاف", r"اختلاف العلماء", r"المذاهب", r"\bdiffer", r"\bdisagree", r"madhhab", r"\bsects?\b"]
GREETING = re.compile(r"^\s*(السلام عليكم[\w\s]*|سلام|مرحبا|مرحباً|أهلا|اهلا|hi|hello|hey|salam|assalamu alaikum|as-salamu alaykum)[\s!.؟?]*$", re.I)
THANKS = re.compile(r"^\s*(شكرا|شكراً|جزاك الله خيرا|جزاكم الله خيرا|thanks|thank you|jazakallah[\w ]*)[\s!.]*$", re.I)
HUMAN = re.compile(r"(أريد|اريد|أبغى|ابغى|ابي)\s+(أتكلم|اتكلم|أتحدث|اتحدث|التحدث|التواصل)|(talk|speak) (to|with) (a |an )?(human|person|da'?i|imam|sheikh|guide)", re.I)


def rule_based_analysis(question: str, ui_lang: str) -> dict:
    lang = "ar" if has_arabic(question) else "en"
    if GREETING.match(question):
        intent = "greeting"
    elif THANKS.match(question):
        intent = "thanks"
    elif HUMAN.search(question):
        intent = "request_human"
    else:
        intent = "question"
    norm = normalize_ar(question).lower()    # «لى» or «يَجوز» must not slip past the patterns
    personal = (any(re.search(normalize_ar(p), norm) for p in PERSONAL_AR)
                or any(re.search(p, question, re.I) for p in PERSONAL_EN)
                or (RULING_WORD.search(norm) is not None and any(re.search(normalize_ar(p), norm) for p in PERSONAL_WEAK)))
    level = "D" if personal else ("C" if any(re.search(p, question, re.I) for p in DISAGREE) else "B")
    quoted = ""
    for rx in (QURAN_BRACKETS_RE, QUOTE_RE):
        m = rx.search(question)
        if m and has_arabic(m.group(1)):
            quoted = m.group(1)
            break
    if level == "B" and RULING_QUESTION.search(question):
        level = "C"
    return {"language": lang, "intent": intent, "level": level, "personal_case": personal, "hostile": False,
            "asks_for_evidence": bool(re.search(r"(دليل|حديث يثبت|آية تثبت|prove|evidence)", question, re.I)),
            "quoted_text": quoted, "quoted_kind": "quran" if quoted and "﴿" in question else ("unclear" if quoted else "none"),
            "standalone_question": question, "queries_ar": [], "queries_en": [],
            "terms": [], "clarify": "", "source": "rules"}


# ---------------------------------------------------------------------------

@dataclass
class AskContext:
    question: str
    ui_lang: str = "ar"
    history: list[dict] = field(default_factory=list)   # [{"role": "user"|"assistant", "text": str}]
    image: bytes | None = None
    image_type: str = ""
    surface: str = "chat"                                 # chat | group
    max_words: int = 180


def _normalize_analysis(a: dict) -> dict:
    """The model's analysis made safe to use: lists are lists of strings, the level is one of A-D, and so on.
    Structured output usually guarantees this, but not every model or provider enforces the schema."""
    a = dict(a or {})
    for k in ("queries_ar", "queries_en", "terms"):
        v = a.get(k)
        a[k] = [str(x) for x in v if isinstance(x, (str, int, float)) and str(x).strip()][:6] if isinstance(v, list) \
            else ([v] if isinstance(v, str) and v.strip() else [])
    level = str(a.get("level") or "B").strip().upper()[:1]
    a["level"] = level if level in ("A", "B", "C", "D") else "B"
    for k in ("language", "intent", "quoted_text", "quoted_kind", "standalone_question", "clarify"):
        a[k] = a[k].strip() if isinstance(a.get(k), str) else ""
    for k in ("personal_case", "hostile", "asks_for_evidence"):
        a[k] = a.get(k) is True
    if a["intent"] not in ("question", "greeting", "thanks", "request_human", "off_topic"):
        a["intent"] = "question"
    return a


def _dedupe_markers(segments: list[dict]) -> list[dict]:
    """Show each verse or hadith card once, where it first appears."""
    seen: set[str] = set()
    out = []
    for s in segments:
        def keep_first(m: re.Match) -> str:
            if m.group(1) in seen:
                return ""
            seen.add(m.group(1))
            return m.group(0)
        out.append({**s, "text": MARKER_RE.sub(keep_first, s["text"])})
    return out


def _safe_clarify(text: str, lang: str) -> str:
    """The analysis' clarifying question is model text shown without grounding, so only a short plain
    question passes; anything else (a claim, a verse, a long text) becomes the fixed one."""
    words = text.split()
    ok = (0 < len(words) <= 25 and text.rstrip().endswith(("?", "؟")) and not MARKER_RE.search(text)
          and not CLAIM_RE.search(normalize_ar(text)) and len(HARAKAT_RE.findall(text)) <= 4
          and not get_matcher().verse_runs(text, min_words=5))
    return text if ok else t("clarify_default", lang)


def _quote_check(texts: list[str]) -> dict | None:
    matcher = get_matcher()
    for text in texts:
        if not text or not looks_like_quote(text):
            continue
        matches = matcher.match(text)
        if not matches:
            return {"input": text, "status": "not_found", "matches": []}
        best = matches[0]
        if best.ambiguous:
            status = "ambiguous"
        elif best.exact:
            status = "exact"
        else:
            status = "differs"
        return {"input": text, "status": status, "matches": [m.as_dict() for m in matches[:3]]}
    return None


def _quote_note(qc: dict) -> str:
    if not qc:
        return ""
    if qc["status"] == "differs":
        m = qc["matches"][0]
        parts = "; ".join(f"{d['type']}: quoted «{d['quoted']}» / reference «{d['reference']}»" for d in m["differences"][:6])
        return (f"The user quoted text matching {', '.join(m['ids'])} but with differences from the reference ({parts}). "
                f"Gently point this out and show the correct verse with its marker.")
    if qc["status"] == "exact":
        return f"The user's quote matches {', '.join(qc['matches'][0]['ids'])} exactly."
    if qc["status"] == "ambiguous":
        return "The user's short quote appears in several verses: " + ", ".join(i for m in qc["matches"] for i in m["ids"]) + "."
    return "The user's quote was not found in the Mushaf; do not treat it as a verse."


def _hadith_sig(p: Passage) -> str:
    """The Prophet's words (the «...» part) as bare letters: the same hadith under two ids, with a
    different chain or punctuation around it, gets the same signature."""
    matn = re.search(r"«([^»]{10,})", p.data["text_ar"])
    return re.sub(r"[^ء-ي]", "", skeleton(matn.group(1) if matn else p.data["text_ar"]))[:80]


def retrieve(analysis: dict, question: str, quote_ids: list[str]) -> tuple[list[Passage], list[dict]]:
    corpus = get_corpus()
    queries = [analysis.get("standalone_question") or question, question]
    queries += analysis.get("queries_ar", [])[:4] + analysis.get("queries_en", [])[:4] + analysis.get("terms", [])[:4]
    raw, dense, retriever = embeddings.search(queries, k=30)  # BM25 + E5 (fused), or BM25 alone
    q_tokens = set(tokens(question + " " + (analysis.get("standalone_question") or "")))
    max_idf = math.log(1 + len(corpus.index.ids))
    chosen: list[Passage] = []
    trace = []
    seen = set()
    for pid in quote_ids:
        p = corpus.get(pid)
        if p and pid not in seen:
            chosen.append(p)
            seen.add(pid)
            trace.append({"id": pid, "score": None, "coverage": 1.0, "via": "quote"})
    terms = corpus.find_terms(question + " " + " ".join(analysis.get("terms", [])))
    for p in terms[:3]:
        if p.id not in seen:
            chosen.append(p)
            seen.add(p.id)
            trace.append({"id": p.id, "score": None, "coverage": None, "via": "glossary"})
    # HadeethEnc lists some hadiths twice (e.g. «بني الإسلام على خمس»)
    seen_text = {_hadith_sig(p) for p in chosen if p.kind == "hadith"}
    per_kind = {"quran": 0, "hadith": 0, "term": 0, "qa": 0, "bayyinat": 0}
    limit = {"quran": 5, "hadith": 4, "term": 2, "qa": 2, "bayyinat": 2}
    for pid, score, _ in raw:
        p = corpus.get(pid)
        if not p or pid in seen or per_kind[p.kind] >= limit[p.kind]:
            continue
        if p.kind == "hadith":
            sig = _hadith_sig(p)
            if sig in seen_text:
                continue
            seen_text.add(sig)
        doc_terms = set(tokens(p.search_text()))
        idf = corpus.index.idf
        total = sum(idf.get(tk, max_idf) for tk in q_tokens) or 1.0
        cov = sum(idf.get(tk, 0.0) for tk in q_tokens if tk in doc_terms) / total
        chosen.append(p)
        seen.add(pid)
        per_kind[p.kind] += 1
        trace.append({"id": pid, "score": round(score, 4 if retriever == "hybrid" else 2), "coverage": round(cov, 2),
                      "dense": dense.get(pid), "via": retriever})
        if len(chosen) >= settings.top_k + len(quote_ids):
            break
    return chosen, trace


def _search_results(passages: list[Passage], lang: str, focus: set[str] | None = None) -> list[dict]:
    return [{"id": p.id, "source": p.url(lang) or p.id, "title": f"{p.id} | {p.title(lang)}",
             "blocks": p.context_blocks(lang, focus=focus)} for p in passages]


def _guard_scripture(text: str, allowed: set[str], trace: dict) -> str:
    """Replace Quran text the model typed with the reference marker; drop what doesn't verify."""
    matcher = get_matcher()

    def verse_marker(span: str) -> str | None:
        found = matcher.match(span)
        if found and found[0].score >= 0.75 and not found[0].ambiguous:
            return "\n" + "\n".join(f"[[{i}]]" for i in found[0].ids) + "\n"
        return None

    def bracket(m: re.Match) -> str:
        if not has_arabic(m.group(1)):
            return m.group(0)     # {braces} around non-Arabic text are not a verse
        marker = verse_marker(m.group(1))
        trace.setdefault("scripture_guard", []).append({"span": m.group(1)[:80], "action": "marker" if marker else "removed"})
        return marker or ""

    text = QURAN_BRACKETS_RE.sub(bracket, text)

    def quote(m: re.Match) -> str:
        span = m.group(1)
        if not has_arabic(span) or len(span.split()) < 3:   # short hadith quotes too («لا نكاح إلا بولي»)
            return m.group(0)
        marker = verse_marker(span)
        if marker:
            trace.setdefault("scripture_guard", []).append({"span": span[:80], "action": "marker"})
            return marker
        norm = normalize_ar(span)
        corpus = get_corpus()
        for pid in allowed:
            p = corpus.get(pid)
            if p and norm in normalize_ar(" ".join(p.context_blocks("ar", full=True) + p.context_blocks("en", full=True))):
                return m.group(0)
        trace.setdefault("unverified_quotes", []).append(span[:120])
        return UNVERIFIED   # a quotation found in no source (a hadith from memory?): its sentence goes

    text = QUOTE_RE.sub(quote, text)

    # Verse text typed without any brackets (7+ words following the Mushaf): the marker, or nothing.
    for a, b in reversed(matcher.verse_runs(text)):
        span = text[a:b]
        found = matcher.match(span)
        exact = found and found[0].score >= 0.9 and not found[0].ambiguous
        marker = "\n" + "\n".join(f"[[{i}]]" for i in found[0].ids) + "\n" if exact else ""
        trace.setdefault("scripture_guard", []).append({"span": span[:80], "action": "marker" if marker else "removed"})
        text = text[:a] + marker + text[b:]

    # Heavily vowelled Arabic outside brackets is almost always a verse typed from memory.
    words = text.split()
    if words and len(HARAKAT_RE.findall(text)) > 25:
        for line in text.split("\n"):
            if len(HARAKAT_RE.findall(line)) > 12 and looks_like_quote(line):
                marker = verse_marker(line)
                if marker:
                    text = text.replace(line, marker.strip())
                    trace.setdefault("scripture_guard", []).append({"span": line[:80], "action": "marker"})
    return text


def _clean_markers(text: str, allowed: set[str], trace: dict) -> str:
    def repl(m: re.Match) -> str:
        if m.group(1) in allowed:
            return m.group(0)
        trace.setdefault("dropped_markers", []).append(m.group(1))
        return ""
    return MARKER_RE.sub(repl, text)


# What may be shown without the model. Precision first: no text is better than an unrelated one.
# E5 similarities, checked by hand on 30 questions (docs/RAG-PLAN.md): an approved answer to the same
# question scores >= 0.86, a verse or hadith on the point >= 0.85, while loosely related or unrelated
# passages crowd 0.80-0.85. A word match alone is not enough (e.g. «دليل/وجود» matched an inheritance hadith).
SHOW_ANSWER = 0.86       # an approved Q&A or Bayyinat answer
SHOW_EXTRA = 0.89        # another passage next to that answer (rarely: the answer usually says it all;
                         # at 0.88 «لا يقبل الله صلاة حائض إلا بخمار» joined a question about prayer during menses)
SHOW_PASSAGE = 0.85      # a verse or hadith when no approved answer is close
SHOW_WORDS = 0.65        # BM25-only installs (no E5): share of the question's words a passage must contain
# A glossary card is shown only when the question asks what a term means, not whenever it names one.
DEFINITION_RE = re.compile(r"(ما|ماذا)\s+(معنى|معني|تعريف|يعني|هو|هي)\b|^\s*(تعريف|معنى|معني)\b"
                           r"|\bwhat\s+(is|are|does)\b|\bmeaning\s+of\b|\bdefine\b", re.I)


def _asks_meaning(question: str, term: Passage) -> bool:
    """«ما معنى التوحيد؟» or "What is Tawhid?": the question is about the term itself. "What are the five
    pillars of Islam?" names a term but asks about something else."""
    m = DEFINITION_RE.search(question)
    if not m:
        return False
    rest = set(tokens(DEFINITION_RE.sub(" ", question)))
    forms = set(tokens(" ".join([term.data["ar"], term.data["en"], *term.data.get("aliases", [])])))
    return bool(rest) and rest <= forms | {"mean", "meaning", "islam", "اسلام", "دين"} and bool(rest & forms)


def _sources_only(passages: list[Passage], lang: str, rtrace: list[dict], question: str = "",
                  show: int = 3) -> list[dict]:
    """The passages that answer the question, shown as they are; [] when none is close enough.

    An approved answer (Q&A or Bayyinat), written for exactly this kind of question, leads and usually
    stands alone; other verses and hadiths join it only when they are very close in meaning.
    """
    coverage = {r["id"]: r["coverage"] or 0 for r in rtrace}
    dense = {r["id"]: r["dense"] for r in rtrace if r.get("dense") is not None}
    terms = [p for p in passages if p.kind == "term" and _asks_meaning(question, p)][:1]
    others = [p for p in passages if p.kind != "term"]
    if dense:   # meaning decides
        answers = sorted((p for p in others if p.kind in ANSWER_KINDS and dense.get(p.id, 0) >= SHOW_ANSWER),
                         key=lambda p: -dense[p.id])
        if answers:
            picks = answers[:1] + [p for p in others if p.kind in ("quran", "hadith")
                                   and dense.get(p.id, 0) >= SHOW_EXTRA][:2]
        else:
            picks = sorted((p for p in others if p.kind in ("quran", "hadith") and dense.get(p.id, 0) >= SHOW_PASSAGE),
                           key=lambda p: -dense[p.id])[:show]
    else:       # words only: they must cover most of the question
        answers = sorted((p for p in others if p.kind in ANSWER_KINDS and coverage.get(p.id, 0) >= SHOW_WORDS),
                         key=lambda p: -coverage[p.id])
        picks = answers[:1] + [p for p in others if p.kind in ("quran", "hadith")
                               and coverage.get(p.id, 0) >= SHOW_WORDS][:show]
    picks = terms + picks
    segs = []
    for p in picks:
        segs.append({"text": f"\n[[{p.id}]]\n", "cites": [p.id]})
    return segs


def ask(ctx: AskContext) -> dict:
    """Answer one question, timing every step: the trace carries the breakdown (milliseconds per step, and
    each model call with its provider, tokens and speed) and the server log gets one line per question."""
    tm = timing.start()
    t0 = time.perf_counter()
    out = _ask(ctx)
    total = time.perf_counter() - t0
    timings = out.setdefault("trace", {}).setdefault("timings", {})
    timings.update({"total": round(total, 2), "steps_ms": dict(tm["steps"]), "llm": list(tm["llm"])})
    tlog.info("ask kind=%s mode=%s | %s", out.get("kind"), out.get("mode"), timing.summary(total))
    return out


def _ask(ctx: AskContext) -> dict:
    t0 = time.perf_counter()
    corpus = get_corpus()
    question = (ctx.question or "").strip()[:MAX_QUESTION_CHARS]
    timings: dict[str, float] = {}
    trace: dict = {"timings": timings}
    notices: list[dict] = []
    llm = None
    try:
        llm = get_claude()
    except LLMUnavailable:
        llm = None
    mode = "ai" if llm else "sources_only"

    # 1. Photo -> text
    ocr = None
    if ctx.image:
        if llm:
            try:
                with timing.step("ocr", llm=True):
                    ocr = assistant.ocr(llm, ctx.image, ctx.image_type or "image/jpeg", ctx.ui_lang)
            except LLMUnavailable as exc:
                log.warning("ocr failed: %s", exc)
        if ocr is None:
            notices.append({"type": "ocr", "text": t("ocr_unavailable", ctx.ui_lang)})
        elif not ocr.get("legible"):
            notices.append({"type": "ocr", "text": t("ocr_illegible", ctx.ui_lang)})
        timings["ocr"] = round(time.perf_counter() - t0, 2)
    if not question and ocr and ocr.get("text"):
        question = ("ما معنى هذا النص؟" if ctx.ui_lang == "ar" else "What does this text mean?")
    if not question:
        return {"kind": "empty", "mode": mode, "lang": ctx.ui_lang, "segments": [], "cards": {}, "sources": [],
                "notices": notices, "ocr": ocr, "quote_check": None, "suggest_daai": False, "level": "A", "trace": trace}

    # 2. Analyse
    t1 = time.perf_counter()
    analysis = None
    quote_report = ""
    if ocr and ocr.get("text"):
        quote_report = ocr["text"]
    if llm:
        try:
            with timing.step("analyze", llm=True):
                raw_analysis = assistant.analyze(llm, question, ctx.history, ctx.ui_lang, quote_report)
            analysis = _normalize_analysis(raw_analysis)
            analysis["source"] = "model"
        except LLMUnavailable as exc:
            log.warning("analyze failed: %s", exc)
    if analysis is None:
        analysis = rule_based_analysis(question, ctx.ui_lang)
        if llm:
            mode = "sources_only"
    # Safety nets whatever the classifier said: obvious personal-case wording is level D, and a yes/no
    # ruling question the classifier didn't call settled (A) gets the disagreement notice (C).
    if analysis.get("level") != "D" and rule_based_analysis(question, ctx.ui_lang)["level"] == "D":
        analysis["level"] = "D"
        analysis["personal_case"] = True
    elif analysis.get("level") == "B" and RULING_QUESTION.search(question):
        analysis["level"] = "C"
    timings["analyze"] = round(time.perf_counter() - t1, 2)
    lang = analysis.get("language") if analysis.get("language") in ("ar", "en") else ctx.ui_lang
    level = analysis.get("level", "B")
    trace["analysis"] = {k: analysis.get(k) for k in ("language", "intent", "level", "personal_case", "hostile",
                                                       "asks_for_evidence", "queries_ar", "queries_en", "terms", "source")}

    base = {"mode": mode, "lang": lang, "level": level, "ocr": ocr, "notices": notices, "trace": trace,
            "cards": {}, "sources": [], "quote_check": None, "suggest_daai": False}

    # 3. Small talk and routing
    intent = analysis.get("intent", "question")
    if intent in ("greeting", "thanks", "off_topic", "request_human") and not ocr:
        return {**base, "kind": intent, "segments": [{"text": t(intent, lang), "cites": []}],
                "suggest_daai": intent in ("request_human", "greeting")}
    if analysis.get("clarify") and level != "D" and not ocr and not analysis.get("quoted_text"):
        return {**base, "kind": "clarify", "segments": [{"text": _safe_clarify(analysis["clarify"], lang), "cites": []}]}

    # 4. Quoted verses (typed or photographed) checked against the Mushaf
    quote_texts = list((ocr or {}).get("quran_segments") or [])
    if ocr and not quote_texts and ocr.get("text"):
        quote_texts.append(ocr["text"])
    if analysis.get("quoted_text") and analysis.get("quoted_kind") != "hadith":
        quote_texts.append(analysis["quoted_text"])   # a hadith is not checked against the Mushaf
    if not quote_texts and has_arabic(question) and looks_like_quote(question) and not INTERROGATIVE_RE.search(question):
        quote_texts.append(question)   # «لماذا خلق الله الشر؟» is a question, not a misquoted verse
    with timing.step("quote_check"):
        qc = _quote_check(quote_texts)
    if qc and qc["status"] == "not_found" and qc["input"] == question:
        qc = None  # a plain Arabic question, not a quote
    quote_ids: list[str] = []
    if qc and qc["matches"]:
        take = qc["matches"][:3] if qc["status"] == "ambiguous" else qc["matches"][:1]
        quote_ids = [i for m in take for i in m["ids"]]
    base["quote_check"] = qc

    # 5. Retrieve
    t2 = time.perf_counter()
    with timing.step("retrieve"):
        passages, rtrace = retrieve(analysis, question, quote_ids)
    timings["retrieve"] = round(time.perf_counter() - t2, 3)
    trace["retrieval"] = rtrace
    allowed = {p.id for p in passages} | {vid for p in passages for vid in p.verse_refs()}
    best_cov = max([r["coverage"] or 0 for r in rtrace if r["via"] in ("bm25", "hybrid")] or [0])
    trace["best_coverage"] = round(best_cov, 2)
    best_dense = max([r.get("dense") or 0 for r in rtrace] or [0])
    on_topic = best_dense >= embeddings.DENSE_STRONG  # a passage close in meaning, even with other words
    trace["best_dense"] = round(best_dense, 3) if best_dense else None

    # 6. Answer
    t3 = time.perf_counter()
    segments: list[dict] = []
    answer: AnswerResult | None = None
    kind = "answer"
    if llm and mode == "ai" and passages:
        # the words of the question and its search phrases pick which parts of a long answer the model reads
        focus = set(tokens(" ".join([question, analysis.get("standalone_question") or ""]
                                    + analysis.get("queries_ar", []) + analysis.get("queries_en", []))))
        notes = []
        if qc:
            notes.append(_quote_note(qc))
        if analysis.get("hostile"):
            notes.append("The tone is hostile. Stay calm and kind, identify the real question and answer it accurately.")
        if analysis.get("asks_for_evidence"):
            notes.append("The user asks for evidence. Cite only evidence present in the results; if none fits, say so.")
        if level == "D":
            notes.append("Personal case: give general information only, no ruling, and recommend asking a qualified scholar.")
        if best_cov < 0.35 and not quote_ids and not on_topic:
            notes.append("Retrieval confidence is low: the results may not answer the question. Abstain unless they clearly do.")
        try:
            with timing.step("answer", llm=True):
                answer = assistant.answer(llm, analysis.get("standalone_question") or question,
                                          _search_results(passages, lang, focus), level, lang, ctx.history, notes,
                                          ctx.max_words)
        except LLMUnavailable as exc:
            log.warning("answer failed: %s", exc)
            mode = "sources_only"
            base["mode"] = mode
    timings["answer"] = round(time.perf_counter() - t3, 2)

    if answer:
        index_to_id = [p.id for p in passages]
        for seg in answer.segments:
            with timing.step("scripture_guard"):
                text = _guard_scripture(seg["text"], allowed, trace)
                text = _clean_markers(text, allowed, trace)
            if UNVERIFIED in text and not settings.strict_grounding:
                text = ""
            cites = []
            for c in seg["citations"]:
                if 0 <= c["index"] < len(index_to_id) and index_to_id[c["index"]] not in cites:
                    cites.append(index_to_id[c["index"]])
            segments.append({"text": text, "cites": cites})
        trace["model"] = answer.model
        trace["usage"] = answer.usage
        if settings.strict_grounding:
            # Only the approved package may speak: drop any model sentence that cites no passage
            # (short connecting phrases such as "and" or "in short" are kept).
            kept, removed = [], []
            for k, s in enumerate(segments):
                plain = MARKER_RE.sub("", s["text"]).replace(UNVERIFIED, "")
                words = len(plain.split())
                markers = MARKER_RE.findall(s["text"])
                if UNVERIFIED in s["text"]:          # quoted a text no source has
                    removed.append(plain.strip()[:200])
                    if markers:
                        kept.append({"text": "\n" + "\n".join(f"[[{m}]]" for m in markers) + "\n", "cites": []})
                    continue
                # A verse/hadith marker in a sentence cites that passage (only retrieved ones survive
                # _clean_markers) - except at level D, where a ruling-like sentence needs a real citation.
                marker_cites = bool(markers) and not (level == "D" and CLAIM_RE.search(normalize_ar(plain)))
                if s["cites"] or words == 0 or marker_cites:
                    kept.append(s)
                    continue
                # a short line introducing the verse or hadith shown right after it («...قوله تعالى:»)
                intro = (plain.rstrip().endswith(":") and words <= INTRO_MAX_WORDS
                         and any(MARKER_RE.search(nxt["text"]) for nxt in segments[k:k + 3]))
                # a short connecting phrase ("In short,"), never a claim, and at level D almost nothing
                connector = (words <= (3 if level == "D" else settings.max_uncited_words)
                             and not CLAIM_RE.search(normalize_ar(plain)))
                if intro or connector:
                    kept.append(s)
                    continue
                removed.append(plain.strip()[:200])
                if markers:                          # the uncited words go; the verses/hadiths they carried stay
                    kept.append({"text": "\n" + "\n".join(f"[[{m}]]" for m in markers) + "\n", "cites": []})
            segments = _dedupe_markers(kept)
            trace["removed_uncited"] = removed
        cited_any = (any(s["cites"] and MARKER_RE.sub("", s["text"]).strip() for s in segments)
                     or any(MARKER_RE.search(s["text"]) for s in segments))
        if not cited_any:
            kind = "abstain"
            segments = [{"text": t("abstain", lang), "cites": []}]  # fixed text, nothing generated
        uncited = [s["text"].strip()[:140] for s in segments
                   if not s["cites"] and len(MARKER_RE.sub("", s["text"]).split()) >= 10]
        words_total = sum(len(MARKER_RE.sub("", s["text"]).split()) for s in segments) or 1
        words_cited = sum(len(MARKER_RE.sub("", s["text"]).split()) for s in segments if s["cites"])
        trace["uncited"] = uncited
        trace["cited_share"] = round(words_cited / words_total, 2)
    else:
        has_term = any(p.kind == "term" for p in passages)
        if level == "D" and not quote_ids:
            # Raw passages next to a personal question read like a ruling on it (e.g. a hadith about
            # a slave marrying without his masters' leave, shown for «أتزوج دون علم أهلي»).
            kind = "refer"
            segments = [{"text": t("personal_no_model", lang), "cites": []}]
        elif not passages or (best_cov < 0.3 and not quote_ids and not has_term and not on_topic):
            kind = "abstain"
            segments = [{"text": t("abstain", lang), "cites": []}]
        elif qc and qc["status"] in ("exact", "differs", "ambiguous"):
            kind = "sources"  # the quote check below shows the matching verse(s)
        else:
            segments = _sources_only(passages, lang, rtrace, question)
            kind = "sources"
            if not segments:   # nothing close enough to show: say so rather than show something unrelated
                kind = "abstain"
                segments = [{"text": t("abstain", lang), "cites": []}]

    # Quote-check verdict leads the answer when the user sent a verse.
    if qc:
        if qc["status"] in ("exact", "differs", "ambiguous"):
            lead_ids = [i for m in qc["matches"][: 3 if qc["status"] == "ambiguous" else 1] for i in m["ids"]]
            lead = {"exact": "quote_found", "differs": "quote_differs", "ambiguous": "quote_ambiguous"}[qc["status"]]
            already = {m.group(1) for s in segments for m in MARKER_RE.finditer(s["text"])}
            missing = [i for i in lead_ids if i not in already]
            if missing:
                segments.insert(0, {"text": t(lead, lang) + "\n" + "\n".join(f"[[{i}]]" for i in missing) + "\n",
                                    "cites": missing})
        elif qc["status"] == "not_found":
            segments.insert(0, {"text": t("quote_not_found", lang) + "\n", "cites": []})

    # 7. Notices and referral
    if level == "D":
        notices.append({"type": "fatwa", "text": t("fatwa", lang)})
    elif level == "C":
        notices.append({"type": "disagreement", "text": t("disagreement", lang)})
    if mode == "sources_only" and kind not in ("abstain", "refer"):
        notices.append({"type": "mode", "text": t("sources_only", lang)})
    if kind == "abstain" and segments and not segments[0]["text"].strip():
        segments = [{"text": t("abstain", lang), "cites": []}]

    used_ids = []
    for s in segments:
        for pid in s["cites"] + [m.group(1) for m in MARKER_RE.finditer(s["text"])]:
            if pid not in used_ids:
                used_ids.append(pid)
    with timing.step("cards"):
        cards = {pid: corpus.get(pid).card(lang) for pid in used_ids if corpus.get(pid)}
    return {**base, "mode": mode, "kind": kind, "segments": segments, "cards": cards, "sources": used_ids,
            "suggest_daai": level in ("C", "D") or kind in ("abstain", "refer") or intent == "request_human"}


def plain_text(answer: dict) -> str:
    """Answer text with markers spelled out, for transcripts and referral cards."""
    out = []
    for s in answer.get("segments", []):
        text = MARKER_RE.sub(lambda m: f"({m.group(1)})", s["text"])
        if s.get("cites"):
            text += " [" + ", ".join(s["cites"]) + "]"
        out.append(text)
    return re.sub(r"\s+", " ", " ".join(out)).strip()

