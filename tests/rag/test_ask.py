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


def test_greeting(client, seeker):
    d = ask(client, seeker, "السلام عليكم")
    assert d["kind"] == "greeting"


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
