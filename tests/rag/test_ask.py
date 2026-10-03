"""The ask pipeline in sources-only mode (no Claude). Owner: Mushari."""
from tests.conftest import seeker_headers


def ask(client, seeker, question, lang="ar"):
    res = client.post("/api/ask", data={"question": question, "lang": lang}, headers=seeker_headers(seeker))
    assert res.status_code == 200, res.text
    return res.json()


def test_misquoted_verse_shows_reference(client, seeker):
    d = ask(client, seeker, "قل هو الله واحد الله الصمد")
    assert d["quote_check"]["status"] == "differs"
    assert {"q:112:1", "q:112:2"} <= set(d["sources"])
    card = d["cards"]["q:112:1"]
    assert card["text_ar"].startswith("قُلۡ هُوَ")      # reference text, not the user's words


def test_personal_case_gets_fatwa_notice(client, seeker):
    d = ask(client, seeker, "هل يجوز لي أن أتزوج دون علم أهلي؟")
    assert d["level"] == "D"
    assert any(n["type"] == "fatwa" for n in d["notices"])
    assert d["suggest_daai"] is True
    # without the model, no raw texts next to a personal question: they would read like a ruling
    assert d["kind"] == "refer" and d["cards"] == {} and not any(s["cites"] for s in d["segments"])


def test_greeting(client, seeker):
    d = ask(client, seeker, "السلام عليكم")
    assert d["kind"] == "greeting"


def test_same_hadith_under_two_ids_shown_once(client, seeker):
    d = ask(client, seeker, "ما أركان الإسلام؟")
    assert not {"h:65000", "h:66512"} <= set(d["sources"])          # «بني الإسلام على خمس» is listed twice
    assert not {"h:65000", "h:66512"} <= {r["id"] for r in d["trace"]["retrieval"]}
    from backend.app.features.rag import pipeline
    from backend.app.features.rag.corpus import get_corpus
    corpus = get_corpus()
    picked, _ = pipeline.retrieve({"standalone_question": "بني الإسلام على خمس"}, "بني الإسلام على خمس",
                                  ["h:65000"])
    assert "h:66512" not in [p.id for p in picked] or "h:65000" not in [p.id for p in picked]


def test_year_is_not_the_sunnah_term():
    from backend.app.features.rag.corpus import get_corpus
    corpus = get_corpus()
    assert not corpus.find_terms("عمري ١٤ سنة وأخاف من أهلي")
    assert [p.id for p in corpus.find_terms("ما هي السنة النبوية؟")] == ["t:sunnah"]


def test_glossary_term_found(client, seeker):
    d = ask(client, seeker, "ما معنى التوحيد؟")
    assert "t:tawhid" in d["sources"]


def test_markers_only_point_to_cards(client, seeker):
    d = ask(client, seeker, "What does the Quran say about kindness to parents?", lang="en")
    import re
    for seg in d["segments"]:
        for pid in re.findall(r"\[\[([^\]]+)\]\]", seg["text"]):
            assert pid in d["cards"]


def test_feedback_and_ownership(client, seeker):
    d = ask(client, seeker, "ما أركان الإسلام؟")
    ok = client.post(f"/api/ask/{d['turn_id']}/feedback", json={"helpful": True}, headers=seeker_headers(seeker))
    assert ok.status_code == 200
    other = client.post("/api/session").json()["token"]
    denied = client.post(f"/api/ask/{d['turn_id']}/feedback", json={"helpful": False}, headers={"X-Seeker": other})
    assert denied.status_code == 404


def test_source_lookup(client):
    card = client.get("/api/sources/q:12:108?lang=ar").json()
    assert card["kind"] == "quran" and card["aya"] == 108


def test_english_link_only_for_translated_hadiths():
    """HadeethEnc has no English page for untranslated hadiths, so the link must fall back to Arabic."""
    from backend.app.features.rag.corpus import get_corpus
    for p in get_corpus().passages.values():
        if p.kind == "hadith" and not p.data["text_en"]:
            assert p.url("en") == p.data["url_ar"]
