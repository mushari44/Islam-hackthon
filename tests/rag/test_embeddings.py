"""Semantic search plumbing (LangChain + FAISS), with a fake embedding model. Owner: Mushari.

The real model (multilingual E5-large) is never loaded here: DeterministicFakeEmbedding gives
identical texts identical vectors, which is enough to test chunking, merging and fusion.
"""
import pytest

pytest.importorskip("langchain")
pytest.importorskip("langchain_community")
pytest.importorskip("faiss")

from langchain_community.vectorstores import FAISS  # noqa: E402
from langchain_community.vectorstores.utils import DistanceStrategy  # noqa: E402
from langchain_core.documents import Document  # noqa: E402
from langchain_core.embeddings import DeterministicFakeEmbedding  # noqa: E402

from backend.app.features.rag import embeddings  # noqa: E402
from backend.app.features.rag.corpus import Passage, get_corpus  # noqa: E402


def _store(docs):
    return FAISS.from_documents(docs, DeterministicFakeEmbedding(size=64),
                                distance_strategy=DistanceStrategy.MAX_INNER_PRODUCT)


def test_long_answers_are_chunked_with_their_question():
    qa = max((p for p in get_corpus().passages.values() if p.kind == "qa"), key=lambda p: len(p.data["answer"]))
    texts = embeddings.passage_texts(qa)
    assert len(texts) > 1                                   # a long answer is several chunks...
    head = embeddings._clean(qa.data["question"])
    assert all(t.startswith(head) for t in texts)           # ...each one saying which question it answers
    assert all("[[" not in t and len(t) <= len(head) + 1 + embeddings.CHUNK_CHARS for t in texts)
    verse = embeddings.passage_texts(get_corpus().get("q:2:256"))
    assert len(verse) == 1 and "التفسير الميسر" in verse[0]


def test_bayyinat_embeds_question_short_and_detailed_answer():
    row = {"id": "b:999", "n": 999, "title": "عنوان", "section": "", "question": "سؤال", "similar": ["صيغة"],
           "gist": "فكرة", "short_answer": "مختصر", "answer": "تفصيل " * 400, "refs": [], "page": 1, "url_ar": ""}
    texts = embeddings.passage_texts(Passage("b:999", "bayyinat", row))
    assert "صيغة" in texts[0] and "مختصر" in texts[1] and len(texts) >= 4


def test_dense_hits_merge_chunks_and_fuse_with_bm25():
    corpus = get_corpus()
    docs = [Document(page_content="zzqx first chunk", metadata={"pid": "qa:36065"}),
            Document(page_content="zzqx second chunk", metadata={"pid": "qa:36065"}),
            Document(page_content="unrelated", metadata={"pid": "q:1:1"}),
            Document(page_content="from an index built elsewhere", metadata={"pid": "b:99999"})]
    Lexical, Dense, Hybrid = embeddings._retriever_classes()
    dense = Dense(store=_store(docs), corpus=corpus, k=10)
    hits = dense.invoke("zzqx first chunk")
    pids = [d.metadata["pid"] for d in hits]
    assert pids[0] == "qa:36065" and pids.count("qa:36065") == 1   # two chunks, one passage
    assert "b:99999" not in pids                                    # ids missing from this corpus are dropped

    hybrid = Hybrid(lexical=Lexical(corpus=corpus), dense=dense)
    fused = hybrid.invoke("zzqx first chunk\nلا إكراه في الدين")
    ids = [d.metadata["pid"] for d in fused]
    assert "qa:36065" in ids                                        # found only by meaning
    assert "q:2:256" in ids                                         # found only by words
    assert len(ids) == len(set(ids))
    top = next(d for d in fused if d.metadata["pid"] == "qa:36065")
    assert top.metadata["dense"] > 0.99 and top.metadata["rrf"] > 0


def test_dense_weighs_70_percent(monkeypatch):
    """With the default weights, a passage ranked first by meaning beats one ranked first by words."""
    corpus = get_corpus()
    Lexical, Dense, Hybrid = embeddings._retriever_classes()
    dense = Dense(store=_store([Document(page_content="zzqx", metadata={"pid": "qa:36065"})]), corpus=corpus)
    hybrid = Hybrid(lexical=Lexical(corpus=corpus), dense=dense)
    assert hybrid.weights == [pytest.approx(0.3), pytest.approx(0.7)]
    fused = hybrid.invoke("zzqx\nلا إكراه في الدين")
    top_bm25 = corpus.index.search(["zzqx", "لا إكراه في الدين"], k=1)[0][0]
    ids = [d.metadata["pid"] for d in fused]
    assert ids[0] == "qa:36065" and ids.index("qa:36065") < ids.index(top_bm25)
    assert fused[0].metadata["rrf"] == pytest.approx(0.7 / 61)

    monkeypatch.setenv("SABEELI_DENSE_WEIGHT", "0.25")
    assert embeddings.dense_weight() == 0.25
    monkeypatch.setenv("SABEELI_DENSE_WEIGHT", "nonsense")
    assert embeddings.dense_weight() == 0.7


def test_search_falls_back_to_bm25(monkeypatch):
    monkeypatch.setattr(embeddings._State, "loaded", True)
    monkeypatch.setattr(embeddings._State, "retriever", None)
    ranked, dense, used = embeddings.search(["لا إكراه في الدين"], k=5)
    assert used == "bm25" and dense == {} and "q:2:256" in [pid for pid, _, _ in ranked]


def test_pipeline_uses_the_hybrid_retriever(monkeypatch):
    from backend.app.features.rag import pipeline

    corpus = get_corpus()
    Lexical, Dense, Hybrid = embeddings._retriever_classes()
    docs = [Document(page_content=t, metadata={"pid": "qa:36130"}) for t in ("why kaaba", "لماذا يتجه المسلمون للكعبة")]
    hybrid = Hybrid(lexical=Lexical(corpus=corpus), dense=Dense(store=_store(docs), corpus=corpus))
    monkeypatch.setattr(embeddings._State, "loaded", True)
    monkeypatch.setattr(embeddings._State, "retriever", hybrid)
    out = pipeline.ask(pipeline.AskContext(question="why kaaba", ui_lang="en"))
    rows = {r["id"]: r for r in out["trace"]["retrieval"]}
    assert rows["qa:36130"]["via"] == "hybrid" and rows["qa:36130"]["dense"] is not None
    # a strong meaning match lets the approved answer lead, even though it shares no word with the question
    assert out["kind"] == "sources" and out["sources"][0] == "qa:36130"
