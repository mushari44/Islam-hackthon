"""Fixes from the overnight audit (4 October): intro lines that carry a ruling, misquoted verse leftovers,
odd photo readings, OpenRouter replies that aren't JSON, plain requests read as quotes, and the database
connection held during model calls. Owner: Mushari. No network: the model is a mocked OpenRouter."""
import httpx
import pytest
from sqlalchemy import event

from backend.app.core import claude as claude_mod
from backend.app.core import openrouter
from backend.app.core.db import engine
from backend.app.features.rag import pipeline
from tests.conftest import seeker_headers
from tests.rag.test_review_fixes import ANALYSIS, _ask, _text


def test_an_intro_line_with_a_ruling_needs_a_citation(monkeypatch):
    d = dict(ANALYSIS, level="D", personal_case=True)
    out = _ask(monkeypatch, "General information only [1].\n"
                            "Your marriage is invalid and you must divorce him today, Allah says:\n[[q:2:256]]\n", d)
    assert "divorce" not in _text(out) and "[[q:2:256]]" in _text(out)
    out = _ask(monkeypatch, "Islam does not force belief [1].\nAllah says:\n[[q:2:256]]\n")
    assert "Allah says:" in _text(out)                      # a plain intro still stays


def test_misquoted_verse_words_after_the_matching_run_go():
    altered = ("لا إكراه في الدين قد تبين الرشد من الغي فمن يكفر بالشيطان ويؤمن بالله فقد استمسك "
               "بالحبل الوثقى [1]")
    out = pipeline._guard_scripture(altered, set(), {})
    assert "[[q:2:256]]" in out and "بالحبل" not in out and "بالشيطان" not in out


def test_an_intro_before_an_inline_verse_keeps_the_verse():
    text = ("قال الله تعالى لا إكراه في الدين قد تبين الرشد من الغي فمن يكفر بالطاغوت ويؤمن بالله فقد "
            "استمسك بالعروة الوثقى لا انفصام لها والله سميع عليم [1]. وهذا يدل على الحرية.")
    out = pipeline._guard_scripture(text, set(), {})
    assert "[[q:2:256]]" in out and "وهذا يدل على الحرية" in out


@pytest.mark.parametrize("raw", [{"text": 12345, "quran_segments": [None, 5], "description": [], "legible": "yes"},
                                 "not a dict", None])
def test_odd_photo_readings_are_normalised(raw):
    o = pipeline._normalize_ocr(raw)
    assert o is None or (o["text"] == "" and o["quran_segments"] == [] and o["legible"] is False)


def test_a_photo_description_with_a_ruling_is_not_shown():
    o = pipeline._normalize_ocr({"text": "x" * 5000, "quran_segments": ["a" * 2000], "legible": True,
                                 "description": "This is haram and you must stop."})
    assert o["description"] == "" and len(o["text"]) == 1500 and len(o["quran_segments"][0]) == 600


def test_a_non_json_200_from_openrouter_is_unavailable_not_a_crash():
    llm = openrouter.OpenRouter.__new__(openrouter.OpenRouter)
    llm.model, llm._schema_ok = "m", True
    llm.http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>busy</html>")))
    with pytest.raises(claude_mod.LLMUnavailable):
        llm.chat("s", "c")


def test_one_unreadable_reply_keeps_the_schema():
    llm = openrouter.OpenRouter.__new__(openrouter.OpenRouter)
    llm.model, llm._schema_ok = "m", True
    reply = {"choices": [{"message": {"content": "not json at all"}, "finish_reason": "stop"}], "usage": {}}
    llm.http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=reply)))
    with pytest.raises(claude_mod.LLMUnavailable):
        llm.json("s", "c", {"type": "object"})
    assert llm._schema_ok is True


@pytest.mark.parametrize("q", ["حدثني عن خلق السماوات والأرض", "اشرح لي معنى التوحيد في الإسلام"])
def test_a_plain_request_is_not_checked_as_a_verse(q):
    out = pipeline.ask(pipeline.AskContext(question=q, ui_lang="ar"))
    assert out["quote_check"] is None


def test_a_new_muslim_asking_to_learn_is_not_a_personal_case():
    assert pipeline.rule_based_analysis("أنا مسلم جديد وأريد تعلم الصلاة", "ar")["level"] != "D"
    assert pipeline.rule_based_analysis("أنا امرأة، هل يجوز لي السفر وحدي؟", "ar")["level"] == "D"


def test_ask_holds_no_database_connection_during_the_model_calls(client, seeker, monkeypatch):
    h = seeker_headers(seeker)
    first = client.post("/api/ask", data={"question": "ما هو التوحيد", "lang": "ar"}, headers=h).json()
    open_now, seen = [0], []

    def out(*_):
        open_now[0] += 1

    def back(*_):
        open_now[0] -= 1
    event.listen(engine, "checkout", out)
    event.listen(engine, "checkin", back)
    real = pipeline.ask

    def spy(ctx):
        seen.append(open_now[0])
        return real(ctx)
    monkeypatch.setattr("backend.app.features.rag.routes.ask", spy)
    try:
        r = client.post("/api/ask", data={"question": "وما أقسامه", "lang": "ar",
                                          "conversation_id": first["conversation_id"]}, headers=h)
    finally:
        event.remove(engine, "checkout", out)
        event.remove(engine, "checkin", back)
    assert r.status_code == 200 and seen == [0]
