"""The question pipeline: read photo -> check quoted verses -> analyse -> retrieve -> answer -> verify.

Safety properties enforced here, not left to the prompt:
  * Scripture shown to the user is rendered from the corpus by id ([[q:..]] / [[h:..]]
    markers); Arabic verse text the model writes itself is swapped for the marker or removed.
  * Markers may only point at passages that were retrieved for this question.
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

from ...core.claude import LLMUnavailable, get_claude
from ...core.config import settings
from ...core.textnorm import has_arabic, normalize_ar, tokens
from . import assistant
from .assistant import AnswerResult
from .corpus import Passage, get_corpus
from .quran_match import get_matcher, looks_like_quote

log = logging.getLogger("sabeeli.pipeline")

MARKER_RE = re.compile(r"\[\[(q:\d{1,3}:\d{1,3}|h:\d+|t:[a-z_]+)\]\]")
QURAN_BRACKETS_RE = re.compile(r"﴿([^﴾]{3,600})﴾")
QUOTE_RE = re.compile(r"[«\"“]([^»\"”]{8,600})[»\"”]")
HARAKAT_RE = re.compile(r"[\u064B-\u0652]")

MAX_QUESTION_CHARS = 2000

TEXT = {
    "greeting": {
        "ar": "وعليكم السلام ورحمة الله. أنا سَبِيلي، مساعد بالذكاء الاصطناعي يجيب عن أسئلتك حول الإسلام من مصادر معتمدة ويُظهرها لك. اسألني عمّا يثير فضولك، أو تحدّث مباشرة مع داعية بلغتك.",
        "en": "Peace be upon you. I'm Sabeeli, an AI assistant that answers questions about Islam from approved sources and shows you those sources. Ask me anything you're curious about, or talk directly with a guide (da'i) in your language.",
    },
    "thanks": {"ar": "حيّاك الله. إن كان لديك سؤال آخر فأنا هنا.", "en": "You're welcome. I'm here if you have another question."},
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

PERSONAL_AR = [r"هل يجوز لي", r"هل يجوز لنا", r"(يجوز|حرام|حلال)\s+(لي|علي|عليّ)", r"\bزوج(ي|تي)\b", r"\bطلاق(ي|ها)?\b",
               r"\bطلقني\b", r"\b(صلاتي|صيامي|زواجي|عقدي|وضوئي|طلاقي|ميراثي)\b", r"في حالتي", r"\bوضعي\b",
               r"\bأنا\s+(مسلم|مسلمة|امرأة|رجل|متزوج|متزوجة|أعيش|اعيش|أعمل|اعمل)", r"ماذا (أفعل|افعل)", r"\bأبي\b.*\b(يجوز|حكم)"]
PERSONAL_EN = [r"\b(can|may|should|must) i\b", r"\bam i allowed\b", r"\bis it (allowed|permissible|haram|halal|ok|okay) for me\b",
               r"\bmy (husband|wife|marriage|divorce|boss|fianc[eé]e?|boyfriend|girlfriend)\b", r"\bin my (case|situation)\b",
               r"\bi (live|work) in\b", r"\bwhat should i do\b"]
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
    personal = any(re.search(p, question) for p in PERSONAL_AR) or any(re.search(p, question, re.I) for p in PERSONAL_EN)
    level = "D" if personal else ("C" if any(re.search(p, question, re.I) for p in DISAGREE) else "B")
    quoted = ""
    for rx in (QURAN_BRACKETS_RE, QUOTE_RE):
        m = rx.search(question)
        if m and has_arabic(m.group(1)):
            quoted = m.group(1)
            break
    return {"language": lang, "intent": intent, "level": level, "personal_case": personal, "hostile": False,
            "asks_for_evidence": bool(re.search(r"(دليل|حديث يثبت|آية تثبت|prove|evidence)", question, re.I)),
            "quoted_text": quoted, "standalone_question": question, "queries_ar": [], "queries_en": [],
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


def retrieve(analysis: dict, question: str, quote_ids: list[str]) -> tuple[list[Passage], list[dict]]:
    corpus = get_corpus()
    queries = [analysis.get("standalone_question") or question, question]
    queries += analysis.get("queries_ar", [])[:4] + analysis.get("queries_en", [])[:4] + analysis.get("terms", [])[:4]
    raw = corpus.index.search(queries, k=30)
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
    per_kind = {"quran": 0, "hadith": 0, "term": 0}
    limit = {"quran": 5, "hadith": 4, "term": 2}
    for pid, score, _ in raw:
        p = corpus.get(pid)
        if not p or pid in seen or per_kind[p.kind] >= limit[p.kind]:
            continue
        doc_terms = set(tokens(p.search_text()))
        idf = corpus.index.idf
        total = sum(idf.get(tk, max_idf) for tk in q_tokens) or 1.0
        cov = sum(idf.get(tk, 0.0) for tk in q_tokens if tk in doc_terms) / total
        chosen.append(p)
        seen.add(pid)
        per_kind[p.kind] += 1
        trace.append({"id": pid, "score": round(score, 2), "coverage": round(cov, 2), "via": "search"})
        if len(chosen) >= settings.top_k + len(quote_ids):
            break
    return chosen, trace


def _search_results(passages: list[Passage], lang: str) -> list[dict]:
    return [{"id": p.id, "source": p.url(lang) or p.id, "title": f"{p.id} | {p.title(lang)}",
             "blocks": p.context_blocks(lang)} for p in passages]


def _guard_scripture(text: str, allowed: set[str], trace: dict) -> str:
    """Replace Quran text the model typed with the reference marker; drop what doesn't verify."""
    matcher = get_matcher()

    def verse_marker(span: str) -> str | None:
        found = matcher.match(span)
        if found and found[0].score >= 0.75 and not found[0].ambiguous:
            return "\n" + "\n".join(f"[[{i}]]" for i in found[0].ids) + "\n"
        return None

    def bracket(m: re.Match) -> str:
        marker = verse_marker(m.group(1))
        trace.setdefault("scripture_guard", []).append({"span": m.group(1)[:80], "action": "marker" if marker else "removed"})
        return marker or ""

    text = QURAN_BRACKETS_RE.sub(bracket, text)

    def quote(m: re.Match) -> str:
        span = m.group(1)
        if not has_arabic(span) or len(span.split()) < 5:
            return m.group(0)
        marker = verse_marker(span)
        if marker:
            trace.setdefault("scripture_guard", []).append({"span": span[:80], "action": "marker"})
            return marker
        norm = normalize_ar(span)
        corpus = get_corpus()
        for pid in allowed:
            p = corpus.get(pid)
            if p and norm in normalize_ar(" ".join(p.context_blocks("ar") + p.context_blocks("en"))):
                return m.group(0)
        trace.setdefault("unverified_quotes", []).append(span[:120])
        return span  # keep the words, drop the quotation marks: it is not a verified quote

    text = QUOTE_RE.sub(quote, text)

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


def _sources_only(passages: list[Passage], lang: str, show: int = 3) -> list[dict]:
    picks = [p for p in passages if p.kind == "term"][:1] + [p for p in passages if p.kind in ("quran", "hadith")][:show]
    segs = []
    for p in picks:
        segs.append({"text": f"\n[[{p.id}]]\n", "cites": [p.id]})
    return segs


def ask(ctx: AskContext) -> dict:
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
            analysis = assistant.analyze(llm, question, ctx.history, ctx.ui_lang, quote_report)
            analysis["source"] = "model"
        except LLMUnavailable as exc:
            log.warning("analyze failed: %s", exc)
    if analysis is None:
        analysis = rule_based_analysis(question, ctx.ui_lang)
        if llm:
            mode = "sources_only"
    # Safety net: obvious personal-case wording is level D whatever the classifier said.
    if analysis.get("level") != "D" and rule_based_analysis(question, ctx.ui_lang)["level"] == "D":
        analysis["level"] = "D"
        analysis["personal_case"] = True
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
        return {**base, "kind": "clarify", "segments": [{"text": analysis["clarify"], "cites": []}]}

    # 4. Quoted verses (typed or photographed) checked against the Mushaf
    quote_texts = list((ocr or {}).get("quran_segments") or [])
    if ocr and not quote_texts and ocr.get("text"):
        quote_texts.append(ocr["text"])
    if analysis.get("quoted_text"):
        quote_texts.append(analysis["quoted_text"])
    if not quote_texts and has_arabic(question) and looks_like_quote(question):
        quote_texts.append(question)
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
    passages, rtrace = retrieve(analysis, question, quote_ids)
    timings["retrieve"] = round(time.perf_counter() - t2, 3)
    trace["retrieval"] = rtrace
    allowed = {p.id for p in passages}
    best_cov = max([r["coverage"] or 0 for r in rtrace if r["via"] == "search"] or [0])
    trace["best_coverage"] = round(best_cov, 2)

    # 6. Answer
    t3 = time.perf_counter()
    segments: list[dict] = []
    answer: AnswerResult | None = None
    kind = "answer"
    if llm and mode == "ai" and passages:
        notes = []
        if qc:
            notes.append(_quote_note(qc))
        if analysis.get("hostile"):
            notes.append("The tone is hostile. Stay calm and kind, identify the real question and answer it accurately.")
        if analysis.get("asks_for_evidence"):
            notes.append("The user asks for evidence. Cite only evidence present in the results; if none fits, say so.")
        if level == "D":
            notes.append("Personal case: give general information only, no ruling, and recommend asking a qualified scholar.")
        if best_cov < 0.35 and not quote_ids:
            notes.append("Retrieval confidence is low: the results may not answer the question. Abstain unless they clearly do.")
        try:
            answer = assistant.answer(llm, analysis.get("standalone_question") or question,
                                      _search_results(passages, lang), level, lang, ctx.history, notes, ctx.max_words)
        except LLMUnavailable as exc:
            log.warning("answer failed: %s", exc)
            mode = "sources_only"
            base["mode"] = mode
    timings["answer"] = round(time.perf_counter() - t3, 2)

    if answer:
        index_to_id = [p.id for p in passages]
        for seg in answer.segments:
            text = _guard_scripture(seg["text"], allowed, trace)
            text = _clean_markers(text, allowed, trace)
            cites = []
            for c in seg["citations"]:
                if 0 <= c["index"] < len(index_to_id) and index_to_id[c["index"]] not in cites:
                    cites.append(index_to_id[c["index"]])
            segments.append({"text": text, "cites": cites})
        trace["model"] = answer.model
        trace["usage"] = answer.usage
        cited_any = any(s["cites"] for s in segments) or any(MARKER_RE.search(s["text"]) for s in segments)
        if not cited_any:
            kind = "abstain"
        uncited = [s["text"].strip()[:140] for s in segments
                   if not s["cites"] and len(MARKER_RE.sub("", s["text"]).split()) >= 10]
        words_total = sum(len(MARKER_RE.sub("", s["text"]).split()) for s in segments) or 1
        words_cited = sum(len(MARKER_RE.sub("", s["text"]).split()) for s in segments if s["cites"])
        trace["uncited"] = uncited
        trace["cited_share"] = round(words_cited / words_total, 2)
    else:
        has_term = any(p.kind == "term" for p in passages)
        if not passages or (best_cov < 0.3 and not quote_ids and not has_term):
            kind = "abstain"
            segments = [{"text": t("abstain", lang), "cites": []}]
        elif qc and qc["status"] in ("exact", "differs", "ambiguous"):
            kind = "sources"  # the quote check below shows the matching verse(s)
        else:
            segments = _sources_only(passages, lang)
            kind = "sources"

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
    if mode == "sources_only" and kind != "abstain":
        notices.append({"type": "mode", "text": t("sources_only", lang)})
    if kind == "abstain" and segments and not segments[0]["text"].strip():
        segments = [{"text": t("abstain", lang), "cites": []}]

    used_ids = []
    for s in segments:
        for pid in s["cites"] + [m.group(1) for m in MARKER_RE.finditer(s["text"])]:
            if pid not in used_ids:
                used_ids.append(pid)
    cards = {pid: corpus.get(pid).card(lang) for pid in used_ids if corpus.get(pid)}
    timings["total"] = round(time.perf_counter() - t0, 2)
    return {**base, "mode": mode, "kind": kind, "segments": segments, "cards": cards, "sources": used_ids,
            "suggest_daai": level in ("C", "D") or kind == "abstain" or intent == "request_human"}


def plain_text(answer: dict) -> str:
    """Answer text with markers spelled out, for transcripts and referral cards."""
    out = []
    for s in answer.get("segments", []):
        text = MARKER_RE.sub(lambda m: f"({m.group(1)})", s["text"])
        if s.get("cites"):
            text += " [" + ", ".join(s["cites"]) + "]"
        out.append(text)
    return re.sub(r"\s+", " ", " ".join(out)).strip()

