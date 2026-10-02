"""The RAG pipeline's Claude requests and response parsing, against a mocked Messages API. Owner: Mushari.

No network and no API key: an httpx MockTransport stands in for api.anthropic.com, records each
request body, and replies with canned responses in the real response format.
"""
import json

import anthropic
import httpx
import pytest

from backend.app.core import claude as claude_mod
from backend.app.features.rag import pipeline


def _message(content, stop="end_turn"):
    return {"id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": content, "stop_reason": stop, "stop_sequence": None,
            "usage": {"input_tokens": 100, "output_tokens": 50}}


ANALYSIS = {"language": "en", "intent": "question", "level": "B", "personal_case": False, "hostile": False,
            "asks_for_evidence": False, "quoted_text": "", "standalone_question": "Is there compulsion in religion?",
            "queries_ar": ["لا إكراه في الدين"], "queries_en": ["no compulsion in religion"], "terms": [], "clarify": ""}


@pytest.fixture()
def mocked(monkeypatch):
    calls = []

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        calls.append({"body": body, "headers": dict(request.headers)})
        if "output_config" in body and "format" in body["output_config"]:
            return httpx.Response(200, json=_message([{"type": "text", "text": json.dumps(ANALYSIS)}]))
        # the answer call: find the search result that holds 2:256 and cite it
        results = [b for b in body["messages"][0]["content"] if b["type"] == "search_result"]
        idx = next(i for i, r in enumerate(results) if r["title"].startswith("q:2:256"))
        return httpx.Response(200, json=_message([
            {"type": "text", "text": "Islam does not force anyone to believe. ",
             "citations": [{"type": "search_result_location", "search_result_index": idx, "source": results[idx]["source"],
                            "title": results[idx]["title"], "cited_text": "There is no compulsion in religion",
                            "start_block_index": 0, "end_block_index": 0}]},
            {"type": "text", "text": "\n[[q:2:256]]\n"},
            {"type": "text", "text": "﴿وَمَا كَانَ لِنَفۡسٍ أَن تُؤۡمِنَ إِلَّا بِإِذۡنِ ٱللَّهِ﴾"},
        ]))

    llm = claude_mod.Claude.__new__(claude_mod.Claude)
    llm.client = anthropic.Anthropic(api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(handler)),
                                     max_retries=0)
    llm.model = "claude-opus-5-5"
    llm._fallbacks = True
    monkeypatch.setattr(pipeline, "get_claude", lambda: llm)
    return calls


def test_answer_is_grounded_and_cited(mocked):
    out = pipeline.ask(pipeline.AskContext(question="Is there compulsion in religion?", ui_lang="en"))
    assert out["mode"] == "ai" and out["kind"] == "answer"

    analyze, answer = mocked[0]["body"], mocked[1]["body"]
    # structured output for the analysis, refusal fallbacks requested on every call
    assert analyze["output_config"]["format"]["type"] == "json_schema"
    assert analyze["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in mocked[0]["headers"].get("anthropic-beta", "")
    # the answer call sends the retrieved passages as citable search results
    results = [b for b in answer["messages"][0]["content"] if b["type"] == "search_result"]
    assert results and all(r["citations"] == {"enabled": True} for r in results)
    assert any(r["title"].startswith("q:2:256") for r in results)
    assert answer["system"][0]["cache_control"] == {"type": "ephemeral"}

    # the citation maps back to the passage id, the marker renders from the corpus
    assert out["segments"][0]["cites"] == ["q:2:256"]
    assert "q:2:256" in out["cards"]
    # Quran text the model typed itself never reaches the user as text: replaced by a marker
    typed = "وَمَا كَانَ لِنَفۡسٍ"
    assert all(typed not in s["text"] for s in out["segments"])
    assert out["trace"]["scripture_guard"]


def test_model_outage_falls_back_to_sources(monkeypatch):
    def broken():
        raise claude_mod.LLMUnavailable("down")
    monkeypatch.setattr(pipeline, "get_claude", broken)
    out = pipeline.ask(pipeline.AskContext(question="ما معنى التوحيد؟", ui_lang="ar"))
    assert out["mode"] == "sources_only" and "t:tawhid" in out["sources"]
