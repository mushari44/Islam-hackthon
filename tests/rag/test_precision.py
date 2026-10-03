"""Only related text is shown. Owner: Mushari.

Without the model, Sabeeli shows passages as they are, so what it shows must answer the question:
nothing is better than something unrelated."""
from backend.app.core.textnorm import tokens
from backend.app.features.rag import pipeline
from backend.app.features.rag.corpus import get_corpus


def ask(q, lang="ar"):
    return pipeline.ask(pipeline.AskContext(question=q, ui_lang=lang))


def test_arabic_question_mark_is_not_part_of_the_word():
    assert tokens("لماذا توقفت النبوة؟") == tokens("لماذا توقفت النبوة")
    assert tokens("الصلاة، والزكاة؛") == tokens("الصلاة والزكاة")


def test_a_question_is_not_checked_as_a_quoted_verse():
    d = ask("لماذا خلق الله الشر؟")
    assert d["quote_check"] is None and "q:29:44" not in d["sources"]
    assert ask("قل هو الله واحد الله الصمد")["quote_check"]["status"] == "differs"   # a real quote still is


def test_glossary_card_only_when_the_question_is_about_the_term():
    assert "t:tawhid" in ask("ما معنى التوحيد؟")["sources"]
    assert "t:islam" not in ask("هل يجبر الإسلام الناس على الدخول فيه؟")["sources"]
    assert "t:islam" not in ask("What are the five pillars of Islam?", "en")["sources"]


def test_off_topic_question_shows_nothing():
    for q in ("من فاز بكأس العالم؟", "ما الطقس اليوم في الرياض؟"):
        d = ask(q)
        assert d["kind"] == "abstain" and d["cards"] == {}


def _row(pid, dense=None, coverage=0.0):
    return {"id": pid, "score": 0, "coverage": coverage, "dense": dense, "via": "hybrid"}


def test_with_meaning_scores_an_approved_answer_stands_alone():
    c = get_corpus()
    passages = [c.get(i) for i in ("qa:36127", "h:65000", "q:2:19", "h:5808")]
    rtrace = [_row("qa:36127", 0.907), _row("h:65000", 0.878), _row("q:2:19", 0.827), _row("h:5808", 0.823)]
    segs = pipeline._sources_only(passages, "ar", rtrace, "ما أركان الإسلام؟")
    assert [s["cites"][0] for s in segs] == ["qa:36127"]          # loosely related passages stay out
    rtrace[1]["dense"] = 0.9
    assert [s["cites"][0] for s in pipeline._sources_only(passages, "ar", rtrace, "")] == ["qa:36127", "h:65000"]


def test_with_meaning_scores_nothing_close_means_nothing_shown():
    c = get_corpus()
    passages = [c.get(i) for i in ("b:9", "q:83:30", "h:3148")] if c.get("b:9") else [c.get(i) for i in ("q:83:30", "h:3148")]
    rtrace = [_row(p.id, 0.84) for p in passages]                 # all below the bars
    assert pipeline._sources_only(passages, "ar", rtrace, "سؤال") == []
