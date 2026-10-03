"""The RAG feature's Claude jobs and prompts.

  analyze() - classify the question (content level A-D, language, personal case)
              and write search queries in Arabic and English (structured output);
  ocr()     - transcribe a photo exactly as written (structured output);
  answer()  - explain using only the retrieved passages, with citations
              (search_result blocks + citations; no structured output).

The verse and hadith text the user sees is never taken from these outputs:
the model refers to passages by id and the app renders them from the corpus.
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field

from ...core.claude import Claude, LLMUnavailable, usage_dict
from ...core.config import settings

LEVELS = """Content levels (from the challenge's scholarly package):
A - settled core information: Quran, authentic hadith, pillars of Islam and faith, basic seerah, ethics, stable introductory facts. Handling: direct answer with its source.
B - explanation, comparison, wisdom behind rulings, intellectual questions and common doubts. Handling: answer from approved material, show the reference, avoid certainty where scholars differ.
C - juristic disagreement, detailed creed issues, contested historical questions, anything needing specialist scholarly treatment. Handling: answer only with what is approved, state that there is disagreement, or refer to a specialist.
D - a personal fatwa or case: a ruling on an individual situation, validity of a specific person's contract or worship, family disputes, legal or medical matters with religious effect. Handling: no ruling; general information only, and referral to a qualified scholar."""

ANALYZE_SYSTEM = f"""You triage questions sent to Sabeeli, an assistant that introduces Islam to curious people and new Muslims using approved sources only. You never answer the question; you only analyse it.

{LEVELS}

Fill every field:
- language: the language the user wrote in ("ar", "en", or "other").
- intent: "question" for anything about Islam or Muslims; "greeting" or "thanks" for small talk; "request_human" if they ask to talk to a person/da'i; "off_topic" if unrelated to Islam.
- level: A, B, C or D as defined above. Questions of the form "is it allowed for me / my husband / in my situation" are D even when phrased generally.
- personal_case: true if the question depends on the user's own circumstances.
- hostile: true if the tone is mocking or aggressive (still a real question to answer calmly).
- asks_for_evidence: true if the user asks for a verse or hadith that proves something.
- quoted_text: Arabic text the user quotes from the Quran or a hadith, copied exactly as they wrote it (keep their mistakes); "" if none.
- standalone_question: the question rewritten to be understandable without the earlier conversation, in the user's language.
- queries_ar / queries_en: 2-4 short keyword searches each, in Arabic and in English, covering the concepts and the usual terms (e.g. Kaaba -> "الكعبة القبلة استقبال", "Ka'bah qiblah direction of prayer"). They search a Quran tafsir, a Quran translation, a hadith encyclopedia and Arabic question-and-answer encyclopedias.
- terms: Islamic terms the answer will likely need (e.g. "التوحيد", "Tawhid").
- clarify: if the question is too vague to search, one short clarifying question in the user's language; otherwise ""."""

ANALYZE_SCHEMA = {
    "type": "object",
    "properties": {
        "language": {"type": "string", "enum": ["ar", "en", "other"]},
        "intent": {"type": "string", "enum": ["question", "greeting", "thanks", "request_human", "off_topic"]},
        "level": {"type": "string", "enum": ["A", "B", "C", "D"]},
        "personal_case": {"type": "boolean"},
        "hostile": {"type": "boolean"},
        "asks_for_evidence": {"type": "boolean"},
        "quoted_text": {"type": "string"},
        "standalone_question": {"type": "string"},
        "queries_ar": {"type": "array", "items": {"type": "string"}},
        "queries_en": {"type": "array", "items": {"type": "string"}},
        "terms": {"type": "array", "items": {"type": "string"}},
        "clarify": {"type": "string"},
    },
    "required": ["language", "intent", "level", "personal_case", "hostile", "asks_for_evidence", "quoted_text",
                 "standalone_question", "queries_ar", "queries_en", "terms", "clarify"],
    "additionalProperties": False,
}

OCR_SYSTEM = """You transcribe text from photos for a verification tool. Accuracy matters more than readability.
- Copy every readable word exactly as it appears, including spelling mistakes and missing words. Never correct, complete or "fix" a verse or hadith from memory.
- Keep diacritics only if they are clearly printed. Mark unreadable parts with "…".
- quran_segments: each part of the text that looks like a quotation from the Quran, copied exactly as in the image (not from memory). [] if none.
- description: one neutral sentence saying what the image shows (e.g. "A wall plaque with Arabic calligraphy"), in the requested language. Do not identify people.
- legible: false if no text can be read."""

OCR_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "quran_segments": {"type": "array", "items": {"type": "string"}},
        "description": {"type": "string"},
        "legible": {"type": "boolean"},
    },
    "required": ["text", "quran_segments", "description", "legible"],
    "additionalProperties": False,
}

ANSWER_SYSTEM = f"""You are Sabeeli (سَبِيلي), an AI assistant that helps curious people and new Muslims understand Islam. You are not a scholar or a mufti, and you say so if asked.

Sources: answer ONLY from the search results in the user's message. They come from the challenge's approved package: the Mushaf text, At-Tafsir Al-Muyassar and the Rowwad translation (QuranEnc), the Encyclopedia of Translated Prophetic Hadiths (HadeethEnc), the approved glossary, the question-and-answer encyclopedias of the Islamic Content Service Association (icadb), and the book «بينات: أسئلة وأجوبة عن الإسلام» (answers to doubts and recurring questions). The Q&A and Bayyinat answers are in Arabic and already show quoted verses as [[q:..]] markers. Do not add religious information from memory.

Rules:
1. Every statement about Islam must be supported by a search result and cited. If the results do not support an answer, or only partly, say plainly what you could not find in the available sources and suggest talking to a da'i (a human guide) in Sabeeli. Never guess.
2. Never type out the Arabic text of a Quran verse or a hadith. To show one, write its marker on its own line: [[q:SURA:AYA]] for a verse or [[h:ID]] for a hadith, using only ids that appear in the search results (including the verse markers inside a Q&A answer). The app displays the exact reference text there. You may explain meanings in your own words, with citations.
3. Never attribute a hadith or saying without its source and grade from the results. If asked for evidence that is not in the results, say that no matching evidence was found in the available sources; never invent one.
4. Do not present matters of scholarly disagreement as settled; mention disagreement only as far as the context needs.
5. Follow the content level you are given:
{LEVELS}
6. Tone: gentle and respectful. Never rebuke the asker. If the question is hostile, stay calm, identify the real question, and answer with wisdom and accuracy without giving up the facts.
7. Explain the core idea before details. For someone new, explain a concept in plain words first, then give the term.
8. Write in the requested answer language. For Islamic terms use the approved equivalents from the glossary results when present (e.g. keep "Tawhid" and explain it) rather than a loose translation.
9. Keep it short: usually 80-180 words, a few short paragraphs, no headings. Do not speculate about the user's own faith, background or other personal traits, and never guess their gender or age: address them neutrally (in Arabic, no يا ابنتي / يا بني / يا أختي / يا أخي and no feminine-only forms), and don't open with a greeting.
10. If the user quoted a verse and the app reports differences from the reference text, point this out gently and show the correct verse with its marker."""


NUMBERED_RULES = """
Citations: the search results are numbered [1], [2], ... End every sentence that says anything about Islam with
the number(s) of the result(s) it relies on, in square brackets, for example [2] or [1][3]: the number, not the id.
Use only results that answer the question, and ignore the others. A sentence without a result number is deleted
before the user sees it, so cite every sentence that states a fact; a short connecting phrase needs none.
Verse and hadith markers such as [[q:2:256]] (double brackets) go on their own line, without a number."""

# One citation: a result number (2) or, as models also write, a result id (qa:36130, q:2:256, b:9).
_REF = r"(?:\d{1,2}|(?:qa|q|h|t|b):[\w:]+)"
# [2], [1, 3], [qa:36130], [b:9، qa:36130] - but never the double-bracket markers [[q:2:256]]
CITE_RE = re.compile(rf"[ \t]*(?<!\[)\[({_REF}(?:\s*[,،]\s*{_REF})*)\](?!\])")
SENTENCE_RE = re.compile(rf"[^.!?؟\n]+(?:[.!?؟]+|$)(?:[ \t]*(?<!\[)\[{_REF}(?:\s*[,،]\s*{_REF})*\](?!\]))*[ \t]*|\n+", re.M)


def numbered_sources(results: list[dict]) -> str:
    """The retrieved passages as numbered sources for a model without Claude's citation feature."""
    out = []
    for n, r in enumerate(results, start=1):
        body = "\n".join(t for t in r["blocks"] if t.strip())
        out.append(f"[{n}] {r['title']}\n{body}")
    return "Search results:\n\n" + "\n\n".join(out)


def parse_numbered(text: str, ids: list[str] | int) -> list[dict]:
    """Model text with [n] (or [result-id]) citations -> segments with citations, one per sentence, in the
    same shape as Claude's. ids: the result ids in order (or just their count). A number or id that isn't
    one of the results cites nothing, so its sentence is dropped like any uncited one."""
    ids = list(ids) if not isinstance(ids, int) else [str(i) for i in range(ids)]
    position = {pid: i for i, pid in enumerate(ids)}
    segments = []
    for m in SENTENCE_RE.finditer(text):
        chunk = m.group(0)
        if not chunk:
            continue
        cites: list[dict] = []
        for group in CITE_RE.findall(chunk):
            for ref in re.split(r"\s*[,،]\s*", group):
                i = int(ref) - 1 if ref.isdigit() else position.get(ref, -1)
                if 0 <= i < len(ids) and i not in [c["index"] for c in cites]:
                    cites.append({"index": i, "cited_text": "", "start": None, "end": None})
        segments.append({"text": CITE_RE.sub("", chunk), "citations": cites})
    return segments


def _answer_numbered(llm, results: list[dict], brief: list[str]) -> "AnswerResult":
    text, data = llm.chat(ANSWER_SYSTEM + "\n" + NUMBERED_RULES,
                          numbered_sources(results) + "\n\n" + "\n".join(brief), max_tokens=2500)
    return AnswerResult(segments=parse_numbered(text, [r["id"] for r in results]),
                        stop_reason=((data.get("choices") or [{}])[0].get("finish_reason") or ""),
                        usage=llm.usage(data), model=data.get("model") or llm.model)


@dataclass
class AnswerResult:
    segments: list[dict]          # [{"text": str, "citations": [{"index", "cited_text", "start", "end"}]}]
    stop_reason: str
    usage: dict = field(default_factory=dict)
    model: str = ""


def _transcript(history: list[dict], limit: int, chars: int) -> str:
    return "\n".join(f"{'User' if t['role'] == 'user' else 'Sabeeli'}: {t['text'][:chars]}" for t in history[-limit:])


def analyze(llm: Claude, question: str, history: list[dict], ui_lang: str, photo_text: str = "") -> dict:
    convo = _transcript(history, 6, 600)
    prompt = (f"Interface language: {ui_lang}\n"
              + (f"Earlier conversation:\n{convo}\n\n" if convo else "")
              + (f"Text read from the user's photo:\n{photo_text}\n\n" if photo_text else "")
              + f"New message:\n{question}")
    return llm.json(ANALYZE_SYSTEM, prompt, ANALYZE_SCHEMA, max_tokens=1500)


def ocr(llm: Claude, image: bytes, media_type: str, lang: str) -> dict:
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                     "data": base64.standard_b64encode(image).decode("ascii")}},
        {"type": "text", "text": f"Transcribe this image. Write the description in {'Arabic' if lang == 'ar' else 'English'}."},
    ]
    return llm.json(OCR_SYSTEM, content, OCR_SCHEMA, max_tokens=3000)


def answer(llm: Claude, question: str, results: list[dict], level: str, answer_lang: str,
           history: list[dict], notes: list[str], max_words: int = 180) -> AnswerResult:
    blocks = [{
        "type": "search_result",
        "source": r["source"],
        "title": r["title"],
        "content": [{"type": "text", "text": t} for t in r["blocks"] if t.strip()],
        "citations": {"enabled": True},
    } for r in results]
    brief = [f"Answer language: {'Arabic' if answer_lang == 'ar' else 'English'}",
             f"Content level: {level}",
             f"Length: at most about {max_words} words"]
    brief += [f"Note: {n}" for n in notes if n]
    convo = _transcript(history, 4, 500)
    if convo:
        brief.append(f"Earlier conversation (for context only):\n{convo}")
    brief.append(f"Question: {question}")
    if getattr(llm, "kind", "anthropic") == "openrouter":
        return _answer_numbered(llm, results, brief)
    resp = llm.create(
        max_tokens=8000,
        system=llm.system(ANSWER_SYSTEM),
        output_config={"effort": settings.answer_effort},
        messages=[{"role": "user", "content": blocks + [{"type": "text", "text": "\n".join(brief)}]}],
    )
    if resp.stop_reason == "refusal":
        raise LLMUnavailable("the model declined this request")
    segments = []
    for b in resp.content:
        if b.type != "text":
            continue
        cites = []
        for c in (getattr(b, "citations", None) or []):
            if getattr(c, "type", "") == "search_result_location":
                cites.append({"index": c.search_result_index, "cited_text": c.cited_text,
                              "start": c.start_block_index, "end": c.end_block_index})
        segments.append({"text": b.text, "citations": cites})
    return AnswerResult(segments=segments, stop_reason=resp.stop_reason or "", usage=usage_dict(resp),
                        model=getattr(resp, "model", llm.model))
