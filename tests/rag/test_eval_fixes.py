"""Fixes from the first run of the evaluation set (eval/cases.csv, 3 October). Owner: Mushari.
No network: the model is a mocked OpenRouter (helpers from test_review_fixes)."""
from backend.app.features.rag import pipeline
from tests.rag.test_review_fixes import ANALYSIS, _ask, _text


def test_a_dropped_not_found_sentence_becomes_the_fixed_notice(monkeypatch):
    out = _ask(monkeypatch, "I could not find anything in the available sources about mining cryptocurrency.\n"
                            "However, Islam does not force belief [1].")
    assert out["kind"] == "answer" and out["trace"].get("partial")
    assert _text(out).startswith(pipeline.t("partial", "en"))
    assert "cryptocurrency" not in _text(out)                     # the model's own words stay dropped
    assert "Islam does not force belief" in _text(out)            # «However,» leaned on the dropped sentence


def test_no_notice_when_nothing_was_said_to_be_missing(monkeypatch):
    out = _ask(monkeypatch, "No, nobody is ever forced to accept Islam in any way at all.\n"
                            "Instead, belief is a free choice [1].")
    assert not out["trace"].get("partial")
    assert "Belief is a free choice" in _text(out)                # the dangling «Instead,» goes with it


def test_a_marker_sentence_and_an_intro_line_are_not_counted_as_uncited(monkeypatch):
    out = _ask(monkeypatch, "Islam does not force belief [1].\n"
                            "The verse that says so, in the chapter of the Cow, reads:\n[[q:2:256]]\n")
    assert out["trace"]["uncited"] == []


def test_personal_wording_is_level_d_without_the_model():
    for q, lang in [("هل يجب علي صيام رمضان وأنا مريض بالسكري؟", "ar"), ("أعمل في بنك، هل راتبي حرام؟", "ar"),
                    ("توفي أبي وترك بيتاً، كم نصيبي؟", "ar"),
                    ("I missed ten days of fasting. What exactly do I have to do now?", "en"),
                    ("He said it three times. Are we still married?", "en")]:
        assert pipeline.rule_based_analysis(q, lang)["level"] == "D", q
    for q, lang in [("ما أركان الإسلام؟", "ar"), ("How does someone become a Muslim?", "en"),
                    ("What do Muslims believe happens after death?", "en")]:
        assert pipeline.rule_based_analysis(q, lang)["level"] != "D", q


def test_the_closest_approved_answer_gets_a_place(monkeypatch):
    """A Q&A answer close in meaning joins the passages even when BM25 ranks it out of the top k."""
    from backend.app.features.rag import embeddings
    from backend.app.features.rag.corpus import get_corpus
    corpus = get_corpus()
    others = [pid for pid in corpus.order if pid.startswith("q:")][:6] + ["h:4560", "h:65000", "h:3417", "h:3133"]
    raw = [(pid, 0.05 - i * 0.001, 0.5) for i, pid in enumerate(others)] + [("qa:36088", 0.01, 0.2)]
    dense = {pid: 0.84 for pid in others} | {"qa:36088": 0.847}
    monkeypatch.setattr(embeddings, "search", lambda queries, k=30: (raw, dense, "hybrid"))
    chosen, trace = pipeline.retrieve(dict(ANALYSIS), "Do Muslims believe Jesus is the son of God?", [])
    assert "qa:36088" in [p.id for p in chosen]
    assert next(r for r in trace if r["id"] == "qa:36088")["via"] == "answer_slot"
    monkeypatch.setattr(pipeline, "ANSWER_SLOT", None)
    chosen, _ = pipeline.retrieve(dict(ANALYSIS), "Do Muslims believe Jesus is the son of God?", [])
    assert "qa:36088" not in [p.id for p in chosen]


def test_a_repeated_verse_marker_still_cites_its_sentence(monkeypatch):
    out = _ask(monkeypatch, "Nobody may be forced into the religion [[q:2:256]]\n"
                            "Guidance has become clear from error, as the same verse goes on to say [[q:2:256]]\n")
    second = next(s for s in out["segments"] if "goes on to say" in s["text"])
    assert "[[q:2:256]]" not in second["text"] and second["cites"] == ["q:2:256"]
    assert out["trace"]["uncited"] == []
