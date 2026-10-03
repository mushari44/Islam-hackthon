"""Fixes from the RAG review (3 October): grounding gaps, the scripture guard, clarify, odd model output,
personal questions without the model, the debug trace and the sentence splitter. Owner: Mushari.
No network: the model is a mocked OpenRouter."""
import json

import httpx
import pytest

from backend.app.core import claude as claude_mod
from backend.app.core import openrouter
from backend.app.features.rag import assistant, pipeline
from tests.conftest import seeker_headers

ANALYSIS = {"language": "en", "intent": "question", "level": "B", "personal_case": False, "hostile": False,
            "asks_for_evidence": False, "quoted_text": "", "quoted_kind": "none",
            "standalone_question": "Is there compulsion in religion?",
            "queries_ar": ["لا إكراه في الدين"], "queries_en": ["no compulsion in religion"], "terms": [], "clarify": ""}


def _reply(text):
    return {"model": "google/gemma-4-31b-it", "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1}}


def _llm(answer_text, analysis=None):
    def handler(request):
        body = json.loads(request.content)
        if "response_format" in body:
            return httpx.Response(200, json=_reply(json.dumps(analysis or ANALYSIS)))
        return httpx.Response(200, json=_reply(answer_text))
    llm = openrouter.OpenRouter.__new__(openrouter.OpenRouter)
    llm.model, llm._schema_ok = "google/gemma-4-31b-it", True
    llm.http = httpx.Client(transport=httpx.MockTransport(handler))
    return llm


def _ask(monkeypatch, answer_text, analysis=None, question="Is there compulsion in religion?"):
    monkeypatch.setattr(pipeline, "get_claude", lambda: _llm(answer_text, analysis))
    return pipeline.ask(pipeline.AskContext(question=question, ui_lang="en"))


def _text(out):
    return "".join(s["text"] for s in out["segments"])


# ---- 1. strict grounding ---------------------------------------------------------------------
def test_a_marker_cites_its_sentence_except_a_ruling_at_level_d(monkeypatch):
    out = _ask(monkeypatch, "Islam does not force belief [1].\nFaith is a free choice, as the verse shows [[q:2:256]]\n")
    assert "free choice" in _text(out)                             # the verse marker cites its sentence
    d = dict(ANALYSIS, level="D", personal_case=True)
    out = _ask(monkeypatch, "General information only [1].\n"
                            "So you must divorce your husband right away [[q:2:256]]\n", d)
    assert "divorce" not in _text(out) and "[[q:2:256]]" in _text(out)   # the words go, the verse stays


def test_short_claims_need_a_citation_and_level_d_keeps_almost_nothing(monkeypatch):
    out = _ask(monkeypatch, "Islam does not force belief [1].\nYour marriage is invalid.\nIn short, ")
    assert "invalid" not in _text(out) and "In short" in _text(out)
    d = dict(ANALYSIS, level="D", personal_case=True)
    out = _ask(monkeypatch, "General information only [1].\nSo you must stop.\nThat would be good for you.\nIn short,", d)
    assert "must stop" not in _text(out) and "good for you" not in _text(out) and "In short" in _text(out)


def test_a_long_intro_line_is_not_an_intro(monkeypatch):
    out = _ask(monkeypatch, "Islam does not force belief [1].\nSo you must divorce your husband immediately, this is "
                            "the final ruling on your case, as the verse says:\n[[q:2:256]]\n")
    assert "divorce" not in _text(out)


# ---- 2. scripture guard ------------------------------------------------------------------------
def test_verse_typed_without_brackets_or_in_braces_becomes_its_marker(monkeypatch):
    out = _ask(monkeypatch, "قال تعالى لا إكراه في الدين قد تبين الرشد من الغي فمن يكفر بالطاغوت [1].\n"
                            "وقال: {قُلْ هُوَ اللَّهُ أَحَدٌ اللَّهُ الصَّمَدُ} [1].")
    text = _text(out)
    assert "الرشد من الغي" not in text and "[[q:2:256]]" in text
    assert "الصمد" not in text.replace("[[", "")


def test_unverified_quoted_hadith_drops_its_sentence(monkeypatch):
    out = _ask(monkeypatch, "Islam does not force belief [1].\nThe Prophet said «من صلى الفجر في جماعة غفر له كل ذنبه» [1].")
    assert "الفجر" not in _text(out)
    assert out["trace"]["unverified_quotes"]


# ---- 3. clarify --------------------------------------------------------------------------------
def test_clarify_is_a_short_plain_question_or_the_fixed_one(monkeypatch):
    bad = dict(ANALYSIS, clarify="Music is haram by consensus and Allah says many things about it, so stop now.")
    out = _ask(monkeypatch, "", bad)
    assert out["kind"] == "clarify" and out["segments"][0]["text"] == pipeline.t("clarify_default", "en")
    good = dict(ANALYSIS, clarify="Do you mean the prayer times or how to pray?")
    assert _ask(monkeypatch, "", good)["segments"][0]["text"] == good["clarify"]


# ---- 5/6. odd model output ----------------------------------------------------------------------
def test_null_lists_and_odd_levels_are_normalised(monkeypatch):
    odd = dict(ANALYSIS, queries_ar=None, queries_en="no compulsion", terms=None, level="d.")
    out = _ask(monkeypatch, "General information only [1].", odd)
    assert out["level"] == "D"


def test_truncated_json_is_unavailable_not_a_crash():
    with pytest.raises(claude_mod.LLMUnavailable):
        openrouter._parse('Sure, here is the JSON: {"language": "en", "intent"')


def test_an_unrelated_400_keeps_the_schema():
    llm = openrouter.OpenRouter.__new__(openrouter.OpenRouter)
    llm.model, llm._schema_ok = "m", True
    llm.http = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(400, json={"error": {"message": "image type not supported"}})))
    with pytest.raises(claude_mod.LLMUnavailable):
        llm.json("s", "c", {"type": "object"})
    assert llm._schema_ok is True


# ---- 7. personal questions without the model -------------------------------------------------------
@pytest.mark.parametrize("q", ["هل يجوز لى أن أتزوج دون علم أهلي؟", "هل يَجوز لي أن أسافر وحدي؟",
                               "Is it ok if I skip fasting because I work nights?",
                               "I am a woman, is it allowed to travel alone?"])
def test_personal_questions_are_level_d_without_the_model(q):
    assert pipeline.rule_based_analysis(q, "ar")["level"] == "D"


@pytest.mark.parametrize("q", ["I am a student, what is Tawhid?", "ما معنى التوحيد؟", "Why is pork forbidden?"])
def test_general_questions_are_not_level_d(q):
    assert pipeline.rule_based_analysis(q, "en")["level"] != "D"


# ---- 8. the browser never receives dropped text --------------------------------------------------
def test_api_response_carries_counts_not_dropped_text(client, seeker, monkeypatch):
    monkeypatch.setattr(pipeline, "get_claude", lambda: _llm("Islam does not force belief [1].\n"
                                                             "An unsupported claim with many words in it here."))
    d = client.post("/api/ask", data={"question": "Is there compulsion in religion?", "lang": "en"},
                    headers=seeker_headers(seeker)).json()
    assert d["trace"]["removed_uncited"] == 1 and "unsupported" not in json.dumps(d)


# ---- 9. sentence splitter --------------------------------------------------------------------------
def test_splitter_keeps_abbreviations_and_moves_lone_citations_back():
    segs = assistant.parse_numbered("Pray five times, e.g. Fajr and Isha [1].\nIt is an obligation.\n[2]", 2)
    texts = [s["text"] for s in segs if s["text"].strip()]
    assert texts[0].startswith("Pray five times, e.g. Fajr and Isha")
    assert [c["index"] for c in segs[0]["citations"]] == [0]
    assert [c["index"] for c in next(s for s in segs if "obligation" in s["text"])["citations"]] == [1]
    clause = assistant.parse_numbered("Claim one [1]; and an extra claim with no source.", 1)
    assert clause[0]["citations"] and not clause[1]["citations"]     # ";" after a citation ends a clause
    joined = assistant.parse_numbered("No, faith is not forced; it is a free choice [1].", 1)
    assert len([s for s in joined if s["text"].strip()]) == 1 and joined[0]["citations"]


def test_each_card_is_shown_once(monkeypatch):
    out = _ask(monkeypatch, "Faith is a free choice [1].\n[[q:2:256]]\nAs said before [1].\n[[q:2:256]]\n")
    assert _text(out).count("[[q:2:256]]") == 1
