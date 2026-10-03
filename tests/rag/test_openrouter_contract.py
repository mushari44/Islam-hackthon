"""The RAG pipeline on OpenRouter (Gemma), against a mocked API. Owner: Mushari.

No network and no key: an httpx MockTransport stands in for openrouter.ai, records each request,
and replies in the OpenAI-compatible response format OpenRouter uses.
"""
import json
import re

import httpx
import pytest

from backend.app.core import claude as claude_mod
from backend.app.core import openrouter
from backend.app.features.rag import assistant, pipeline

ANALYSIS = {"language": "en", "intent": "question", "level": "B", "personal_case": False, "hostile": False,
            "asks_for_evidence": False, "quoted_text": "", "standalone_question": "Is there compulsion in religion?",
            "queries_ar": ["لا إكراه في الدين"], "queries_en": ["no compulsion in religion"], "terms": [], "clarify": ""}


def _reply(text, model="google/gemma-4-31b-it"):
    return {"id": "gen-1", "model": model, "choices": [{"message": {"role": "assistant", "content": text},
                                                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 40}}


def _client(handler):
    llm = openrouter.OpenRouter.__new__(openrouter.OpenRouter)
    llm.model, llm._schema_ok = "google/gemma-4-31b-it", True
    llm.http = httpx.Client(transport=httpx.MockTransport(handler), headers={"Authorization": "Bearer test"})
    return llm


@pytest.fixture()
def calls(monkeypatch):
    seen = []

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        seen.append(body)
        if "response_format" in body:
            return httpx.Response(200, json=_reply(json.dumps(ANALYSIS)))
        sources = body["messages"][1]["content"]
        numbers = dict(re.findall(r"^\[(\d+)\] (\S+) \|", sources, re.M))   # "[3] q:2:256 | Quran 2:256 ..."
        n = next(num for num, pid in numbers.items() if pid == "q:2:256")
        return httpx.Response(200, json=_reply(
            f"Islam does not force anyone to believe [{n}].\n[[q:2:256]]\n"
            "Most historians also agree that this verse was revealed in the second year of the Hijra in Madinah.\n"
            "In short, "))

    monkeypatch.setattr(pipeline, "get_claude", lambda: _client(handler))
    return seen


def test_gemma_answer_is_grounded_by_numbered_citations(calls):
    out = pipeline.ask(pipeline.AskContext(question="Is there compulsion in religion?", ui_lang="en"))
    assert out["mode"] == "ai" and out["kind"] == "answer"
    analyze, answer = calls[0], calls[1]
    assert analyze["response_format"]["type"] == "json_schema"
    assert analyze["provider"] == {"data_collection": "deny", "sort": "throughput"}   # private providers, fastest first
    assert answer["messages"][1]["content"].startswith("Search results:\n\n[1] ")
    assert "Citations:" in answer["messages"][0]["content"]
    first = out["segments"][0]
    assert first["cites"] == ["q:2:256"] and "[" not in first["text"]   # [n] became a citation, not text
    assert "q:2:256" in out["cards"]
    # the uncited claim is dropped by strict grounding; the short connector stays
    assert all("historians" not in s["text"] for s in out["segments"])
    assert any("historians" in r for r in out["trace"]["removed_uncited"])
    assert out["trace"]["model"] == "google/gemma-4-31b-it"


def test_images_become_openai_parts():
    parts = openrouter.OpenRouter._content([
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}},
        {"type": "text", "text": "Transcribe this image."}])
    assert parts[0] == {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}
    assert parts[1] == {"type": "text", "text": "Transcribe this image."}


def test_json_falls_back_when_schema_output_is_rejected():
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body["response_format"]["type"])
        if body["response_format"]["type"] == "json_schema":
            return httpx.Response(400, json={"error": {"message": "response_format json_schema not supported"}})
        return httpx.Response(200, json=_reply("```json\n" + json.dumps({"ok": True}) + "\n```"))

    llm = _client(handler)
    assert llm.json("sys", "hi", {"type": "object"}) == {"ok": True}
    assert seen == ["json_schema", "json_object"]
    assert llm.json("sys", "again", {"type": "object"}) == {"ok": True}
    assert seen[-1] == "json_object"                                    # remembered: no second failed try


def test_errors_mean_sources_only(monkeypatch):
    llm = _client(lambda request: httpx.Response(401, json={"error": {"message": "bad key"}}))
    with pytest.raises(claude_mod.LLMUnavailable):
        llm.chat("sys", "hi")
    monkeypatch.setattr(pipeline, "get_claude", lambda: llm)
    out = pipeline.ask(pipeline.AskContext(question="ما معنى التوحيد؟", ui_lang="ar"))
    assert out["mode"] == "sources_only"


def test_parse_numbered_keeps_every_line():
    text = "Faith is a choice [1, 3]. It is stated clearly. [2]\n[[q:2:256]]\nUncited line"
    segs = assistant.parse_numbered(text, 3)
    assert [c["index"] for c in segs[0]["citations"]] == [0, 2]
    assert [c["index"] for c in segs[1]["citations"]] == [1]
    assert "".join(s["text"] for s in segs).replace(" ", "") == \
        "Faithisachoice.Itisstatedclearly.\n[[q:2:256]]\nUncitedline"
    assert assistant.parse_numbered("Bad number [9].", 3)[0]["citations"] == []


def test_ids_count_as_citations_too():
    ids = ["b:9", "qa:36130", "q:4:129"]
    segs = assistant.parse_numbered("They circle it in obedience to God [b:9, qa:36130]. Fairness is required "
                                    "[[q:4:3]][q:4:129]. Unknown [qa:99999].", ids)
    assert [ids[c["index"]] for c in segs[0]["citations"]] == ["b:9", "qa:36130"]
    assert [ids[c["index"]] for c in segs[1]["citations"]] == ["q:4:129"] and "[[q:4:3]]" in segs[1]["text"]
    assert segs[2]["citations"] == []


def test_a_line_introducing_a_verse_stays(monkeypatch):
    def handler(request):
        body = json.loads(request.content)
        if "response_format" in body:
            return httpx.Response(200, json=_reply(json.dumps(ANALYSIS)))
        return httpx.Response(200, json=_reply(
            "Islam does not force anyone to believe [1].\nThe Quran states this principle very clearly in the verse:\n"
            "[[q:2:256]]\nEveryone in history has always agreed with this view without any exception at all."))

    monkeypatch.setattr(pipeline, "get_claude", lambda: _client(handler))
    out = pipeline.ask(pipeline.AskContext(question="Is there compulsion in religion?", ui_lang="en"))
    text = "".join(s["text"] for s in out["segments"])
    assert "states this principle" in text and "[[q:2:256]]" in text
    assert "history" not in text


def test_a_passing_failure_is_retried_once_and_a_bad_key_is_not(monkeypatch):
    monkeypatch.setattr(openrouter, "RETRY_WAIT", 0)
    replies = [httpx.Response(503, text="overloaded"), httpx.Response(200, json=_reply("fine"))]
    seen = []

    def flaky(request):
        seen.append(1)
        return replies.pop(0)
    text, _ = _client(flaky).chat("system", "hello")
    assert text == "fine" and len(seen) == 2

    seen.clear()

    def bad_key(request):
        seen.append(1)
        return httpx.Response(401, text="no")
    with pytest.raises(claude_mod.LLMUnavailable):
        _client(bad_key).chat("system", "hello")
    assert len(seen) == 1

    seen.clear()

    def always_down(request):
        seen.append(1)
        return httpx.Response(502, text="bad gateway")
    with pytest.raises(claude_mod.LLMUnavailable):
        _client(always_down).chat("system", "hello")
    assert len(seen) == 2
