"""The approved Q&A sources: icadb's two Q&A encyclopedias and the book Bayyinat. Owner: Mushari.

Bayyinat's extracted text is built locally (its rights are reserved, so it isn't in git); the tests
that need it use a synthetic row, and the extraction rules are tested on synthetic strings.
"""
import importlib.util
import re
from pathlib import Path

from backend.app.features.rag import pipeline
from backend.app.features.rag.corpus import Passage, get_corpus

ROOT = Path(__file__).resolve().parents[2]
MARKER = re.compile(r"\[\[(q:\d{1,3}:\d{1,3})\]\]")


def _script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_qa_items_load_and_their_verses_exist():
    corpus = get_corpus()
    items = [p for p in corpus.passages.values() if p.kind == "qa"]
    assert len(items) == 543
    for p in items:
        for vid in MARKER.findall(p.data["answer"]):
            assert corpus.get(vid), (p.id, vid)       # every verse marker renders from the Mushaf
            assert vid in p.data["refs"]
        assert p.url("en") == p.data["url_ar"]  # published in Arabic only


def test_qa_card_shows_verses_from_the_mushaf():
    card = get_corpus().get("qa:36065").card("ar")
    assert card["kind"] == "qa" and card["question"]
    assert "q:7:54" in card["verses"]
    assert card["verses"]["q:7:54"]["text_ar"] == get_corpus().get("q:7:54").data["text_ar"]
    assert "﴿" not in card["answer"].split("[[q:7:54]]")[0]  # the quoted verse became a marker


def test_long_answer_gives_the_model_its_matching_lines():
    from backend.app.core.textnorm import tokens
    qa = max((p for p in get_corpus().passages.values() if p.kind == "qa"), key=lambda p: len(p.data["answer"]))
    lines = [x.strip() for x in qa.data["answer"].split("\n") if x.strip()]
    target = next(x for x in reversed(lines) if len(tokens(x)) >= 5)    # a line near the end
    plain = qa.context_blocks("ar")
    focused = qa.context_blocks("ar", focus=set(tokens(target)))
    assert target not in plain and target in focused                    # it is beyond the budget otherwise
    assert focused[1] == lines[0] and "(…)" in focused                  # the opening stays; gaps are marked
    assert sum(map(len, focused[1:])) <= 4000 + 50
    assert target in qa.context_blocks("ar", full=True)


def test_doubt_question_retrieves_an_approved_answer():
    out = pipeline.ask(pipeline.AskContext(question="لماذا يعبد المسلمون الكعبة؟", ui_lang="ar"))
    retrieved = [r["id"] for r in out["trace"]["retrieval"]]
    assert any(i.startswith("qa:") for i in retrieved)
    # sources-only mode leads with the approved answer when it covers the question
    assert out["sources"][0].startswith(("qa:", "b:"))


def test_verses_inside_a_retrieved_answer_may_be_shown():
    qa = get_corpus().get("qa:36065")
    allowed = {qa.id} | set(qa.verse_refs())
    trace = {}
    kept = pipeline._clean_markers("انظر:\n[[q:7:54]]\n[[q:2:255]]", allowed, trace)
    assert "[[q:7:54]]" in kept and "[[q:2:255]]" not in kept
    assert trace["dropped_markers"] == ["q:2:255"]


def test_icadb_verse_resolution():
    icadb = _script("ingest_icadb")
    assert icadb.verse_markers("ٱلۡقَارِعَةُ ١ مَا ٱلۡقَارِعَةُ ٢") == ["q:101:1", "q:101:2"]
    # a phrase found in several verses is settled by the aya number the source gives
    assert icadb.verse_markers("هُوَ ٱلَّذِيٓ أَرۡسَلَ رَسُولَهُۥ بِٱلۡهُدَىٰ وَدِينِ ٱلۡحَقِّ لِيُظۡهِرَهُۥ عَلَى ٱلدِّينِ كُلِّهِۦ وَلَوۡ كَرِهَ ٱلۡمُشۡرِكُونَ٣٣") == ["q:9:33"]
    assert icadb.verse_markers("ٱلۡحَمۡدُ لِلَّهِ رَبِّ ٱلۡعَٰلَمِينَ") is None   # ambiguous: left as written
    assert icadb._is_sura_ref("[الأعراف ٥٤].") and icadb._is_sura_ref("[سورة البروج: 16]")
    assert not icadb._is_sura_ref("[صحيح مسلم (2647)].")


def test_bayyinat_verse_references():
    bay = _script("ingest_bayyinat")
    v = bay.VERSE
    refs, report = [], []
    text = bay.place_verses(f"قال تعالى: ﴿{v} {v}\n{v}﴾ [يس: 40]، وقال: ﴿{v}﴾ [النمل: 54-53]. وفي قوله: ﴿{v}﴾ عبرة.",
                            refs, report, "b:0")
    assert refs == ["q:36:40", "q:27:53", "q:27:54"]
    assert "[يس" not in text and "[[q:36:40]]" in text
    assert "﴿…﴾" in text and len(report) == 1   # a verse with no reference is never guessed


def test_bayyinat_passage_card():
    row = {"id": "b:999", "n": 999, "title": "سؤال تجريبي", "section": "قسم تجريبي", "question": "ما الدليل؟",
           "similar": ["صيغة أخرى"], "gist": "الفكرة", "short_answer": "جواب مختصر\n[[q:112:1]]",
           "answer": "جواب مفصل", "refs": ["q:112:1"], "page": 10, "url_ar": "https://dawa.center/file/7937"}
    p = Passage(row["id"], "bayyinat", row)
    card = p.card("en")
    assert card["short_answer"] and "q:112:1" in card["verses"]
    assert card["url"] == "https://dawa.center/file/7937"
    blocks = p.context_blocks("en")
    assert blocks[0].startswith("[Bayyinat b:999]") and "[[q:112:1]]" in blocks
    assert "صيغة أخرى" in p.search_text()
