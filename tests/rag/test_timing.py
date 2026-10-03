"""Every answer says how long each step took, so a slow answer shows its slow step. Owner: Mushari."""
from backend.app.core import timing
from backend.app.features.rag import pipeline


def test_answer_carries_step_timings():
    d = pipeline.ask(pipeline.AskContext(question="ما أركان الإسلام؟", ui_lang="ar"))
    t = d["trace"]["timings"]
    assert t["total"] >= 0 and "retrieve" in t["steps_ms"] and "bm25" in t["steps_ms"]
    assert t["llm"] == []          # sources-only mode in tests: no model call to time


def test_model_calls_are_labelled_by_the_step_they_belong_to():
    timing.start()
    with timing.step("answer", llm=True):
        timing.llm_call("SomeHost", "m", 2.0, 1000, 300)
    with timing.step("retrieve"):
        pass
    cur = timing.current()
    assert cur["llm"][0]["step"] == "answer" and cur["llm"][0]["tok_s"] == 150.0
    assert "SomeHost 1000->300 tok, 150.0 tok/s" in timing.summary(2.0)
