"""Semantic search with multilingual E5-large, fused with BM25 through LangChain. Owner: Mushari.

Why: BM25 only finds passages that share words with the question. "Why do Muslims
pray towards Mecca?" and «لماذا يتجه المسلمون إلى الكعبة» share no word with the
tafsir of 2:144, and a Q&A item can answer a doubt in different words from the asker.
A multilingual embedding model puts Arabic and English text with the same meaning
close together, so the two searches complement each other.

The pieces are standard LangChain parts:
  * E5Embeddings     - a LangChain Embeddings over sentence-transformers, adding the
                       "query: " / "passage: " prefixes E5 was trained with;
  * the vector store - LangChain's FAISS wrapper, inner product on normalised vectors
                       (= cosine), built once by scripts/build_embeddings.py;
  * LexicalRetriever - our Arabic-aware BM25 index as a LangChain retriever;
  * DenseRetriever   - FAISS search for every query, chunk hits merged per passage;
  * HybridRetriever  - both, fused with LangChain's EnsembleRetriever (weighted
                       reciprocal rank fusion, deduplicated by passage id).

Retrieval units stay the same as everywhere else: a hit is a whole passage id
(q:2:256, h:2962, qa:36065, b:12). Long passages are embedded in several chunks
only so that each part of a long answer can be found; the chunks never reach
the model or the user.

Everything here is optional. Without the packages (requirements-embeddings.txt)
or without a built index, search() falls back to BM25 alone, and the app works
exactly as before. SABEELI_EMBEDDINGS: "auto" (default: use the index if it is
built), "1" (same, and log loudly if it can't be used) or "0" (BM25 only).
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path

from ...core.config import settings
from ...core.textnorm import strip_marks
from .corpus import Corpus, Passage, get_corpus

log = logging.getLogger("sabeeli.embeddings")

DEFAULT_MODEL = "intfloat/multilingual-e5-large"
CHUNK_CHARS = 900          # E5 reads at most 512 tokens; ~900 Arabic characters stay well inside that
CHUNK_OVERLAP = 120
DENSE_K = 60               # chunk hits per query before merging them into passages
MAX_QUERIES = 12           # the question, its standalone form, and the analysis' Arabic/English phrases
# E5 similarities sit in a narrow band: unrelated text ~0.80-0.83, a passage about the same question
# ~0.86-0.90 (checked by hand on a few questions). Above this, a passage counts as on-topic even
# when it shares no word with the question. Tune on the evaluation set.
DENSE_STRONG = 0.86
RRF_C = 60                 # the usual reciprocal-rank-fusion constant
MARKERS = re.compile(r"\[\[[a-z]{1,2}:[\w:]+\]\]")


def model_name() -> str:
    return os.getenv("SABEELI_EMBED_MODEL", DEFAULT_MODEL)


def mode() -> str:
    return os.getenv("SABEELI_EMBEDDINGS", "auto").strip().lower()


def index_dir() -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", model_name().lower()).strip("-")
    return settings.data_dir / "cache" / "vectors" / slug


# ---------------------------------------------------------------------------
# What gets embedded for each passage
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    """Plain text for the encoder: no vowel marks, no [[markers]], single spaces."""
    return re.sub(r"\s+", " ", MARKERS.sub(" ", strip_marks(text or ""))).strip()


def _chunks(head: str, body: str) -> list[str]:
    """The heading repeated on every chunk of a long body, so each chunk says what it is about."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    body = _clean(body)
    if not body:
        return [head]
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_CHARS, chunk_overlap=CHUNK_OVERLAP,
                                              separators=["\n\n", "\n", ".", "،", "؛", " ", ""])
    return [f"{head}\n{part}" for part in splitter.split_text(body)]


def passage_texts(p: Passage) -> list[str]:
    """The texts that stand for one passage in the vector index."""
    d = p.data
    if p.kind == "quran":
        return [f"{d['sura_name_ar']} {d['aya']}: {_clean(d['text_ar'])}\nالتفسير الميسر: {_clean(d['tafsir_ar'])}\n"
                f"{d['translation_en']}"]
    if p.kind == "hadith":
        texts = [f"{_clean(d['title_ar'])}\n{_clean(d['text_ar'])}\n{_clean(d['explanation_ar'])[:CHUNK_CHARS]}"]
        if d.get("text_en"):
            texts.append(f"{d.get('title_en', '')}\n{d['text_en']}\n{(d.get('explanation_en') or '')[:CHUNK_CHARS]}")
        return texts
    if p.kind == "term":
        return [f"{d['ar']} - {d['en']} ({', '.join(d.get('aliases') or [])}): {d['rule_ar']}"]
    if p.kind == "qa":
        return _chunks(_clean(d["question"]), d["answer"])
    if p.kind == "bayyinat":
        head = _clean(d["title"])
        return ([f"{head}\n{_clean(d['question'])}\n" + "\n".join(_clean(s) for s in d.get("similar") or []),
                 f"{head}\n{_clean(d['gist'])}\n{_clean(d['short_answer'])}"[:CHUNK_CHARS * 2]]
                + _chunks(head, d["answer"]))
    return []


def documents(corpus: Corpus) -> list:
    from langchain_core.documents import Document

    return [Document(page_content=text, metadata={"pid": pid, "kind": corpus.passages[pid].kind})
            for pid in corpus.order for text in passage_texts(corpus.passages[pid])]


# ---------------------------------------------------------------------------
# LangChain components
# ---------------------------------------------------------------------------

def _embeddings_class():
    from langchain_core.embeddings import Embeddings

    class E5Embeddings(Embeddings):
        """multilingual-e5-large through sentence-transformers, with E5's query/passage prefixes."""

        def __init__(self, name: str, device: str | None = None, batch_size: int = 32):
            import torch
            from sentence_transformers import SentenceTransformer

            self.device = device or os.getenv("SABEELI_EMBED_DEVICE") or ("cuda" if torch.cuda.is_available() else "cpu")
            self.model = SentenceTransformer(name, device=self.device)
            self.batch_size = batch_size

        def _encode(self, texts: list[str]) -> list[list[float]]:
            vecs = self.model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True,
                                     convert_to_numpy=True, show_progress_bar=len(texts) > 500)
            return vecs.tolist()

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return self._encode([f"passage: {t}" for t in texts])

        def embed_query(self, text: str) -> list[float]:
            return self._encode([f"query: {text}"])[0]

        def embed_queries(self, texts: list[str]) -> list[list[float]]:
            """All of a question's search phrases in one batch."""
            return self._encode([f"query: {t}" for t in texts])

    return E5Embeddings


def _retriever_classes():
    from langchain.retrievers import EnsembleRetriever
    from langchain_core.callbacks import CallbackManagerForRetrieverRun
    from langchain_core.documents import Document
    from langchain_core.retrievers import BaseRetriever

    def lines(query: str) -> list[str]:
        return [q for q in (x.strip() for x in query.split("\n")) if q]

    class LexicalRetriever(BaseRetriever):
        """Sabeeli's BM25 index (Arabic normalisation, light stemming) as a LangChain retriever.
        The query is one search phrase per line, like the pipeline's analysis produces."""
        corpus: Corpus
        k: int = 40

        def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[Document]:
            return [Document(page_content=pid, metadata={"pid": pid, "bm25": score, "coverage": cov})
                    for pid, score, cov in self.corpus.index.search(lines(query), k=self.k)]

    class DenseRetriever(BaseRetriever):
        """FAISS search for every query line; a passage scores its best chunk across all lines."""
        store: object
        corpus: Corpus
        k: int = 40

        def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[Document]:
            best: dict[str, float] = {}
            qs = lines(query)[:MAX_QUERIES]
            emb = self.store.embedding_function
            vecs = emb.embed_queries(qs) if hasattr(emb, "embed_queries") else [emb.embed_query(q) for q in qs]
            for vec in vecs:
                for doc, score in self.store.similarity_search_with_score_by_vector(vec, k=DENSE_K):
                    pid = doc.metadata["pid"]
                    if pid in self.corpus.passages and score > best.get(pid, -1.0):
                        best[pid] = float(score)
            ranked = sorted(best.items(), key=lambda kv: -kv[1])[: self.k]
            return [Document(page_content=pid, metadata={"pid": pid, "dense": s}) for pid, s in ranked]

    class HybridRetriever(BaseRetriever):
        """BM25 and dense results fused by LangChain's weighted reciprocal rank (dedup by passage id)."""
        lexical: BaseRetriever
        dense: BaseRetriever
        weights: list[float] = [0.5, 0.5]

        def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[Document]:
            lex = self.lexical.invoke(query)
            den = self.dense.invoke(query)
            ensemble = EnsembleRetriever(retrievers=[self.lexical, self.dense], weights=self.weights,
                                         c=RRF_C, id_key="pid")
            fused = ensemble.weighted_reciprocal_rank([lex, den])
            info: dict[str, dict] = {}
            for doc in lex + den:
                info.setdefault(doc.metadata["pid"], {}).update(doc.metadata)
            rank = {}
            for weight, docs in zip(self.weights, (lex, den)):
                for r, doc in enumerate(docs, start=1):
                    pid = doc.metadata["pid"]
                    rank[pid] = rank.get(pid, 0.0) + weight / (r + RRF_C)
            return [Document(page_content=d.metadata["pid"], metadata={**info[d.metadata["pid"]],
                                                                       "rrf": rank[d.metadata["pid"]]})
                    for d in fused]

    return LexicalRetriever, DenseRetriever, HybridRetriever


# ---------------------------------------------------------------------------
# Build, load, search
# ---------------------------------------------------------------------------

def _stamp(corpus: Corpus) -> dict:
    return {"model": model_name(), "passages": len(corpus.order),
            "files": {f.name: f.stat().st_size for f in sorted(settings.corpus_dir.glob("*.jsonl"))}}


def build_index(batch_size: int = 64) -> dict:
    """Embed every passage and save the FAISS index (scripts/build_embeddings.py)."""
    from langchain_community.vectorstores import FAISS
    from langchain_community.vectorstores.utils import DistanceStrategy

    corpus = get_corpus()
    docs = documents(corpus)
    t0 = time.perf_counter()
    emb = _embeddings_class()(model_name(), batch_size=batch_size)
    store = FAISS.from_documents(docs, emb, distance_strategy=DistanceStrategy.MAX_INNER_PRODUCT)
    out = index_dir()
    out.mkdir(parents=True, exist_ok=True)
    store.save_local(str(out))
    stamp = {**_stamp(corpus), "chunks": len(docs), "device": emb.device, "seconds": round(time.perf_counter() - t0, 1)}
    (out / "stamp.json").write_text(json.dumps(stamp, indent=1), encoding="utf-8")
    return stamp


class _State:
    lock = threading.Lock()
    loaded = False
    retriever = None
    reason = ""


def _load(wait: bool = False):
    """The hybrid retriever, or None (with the reason kept for status()).

    A request that arrives while the model is still loading (about 15 s after start-up) doesn't
    wait for it: it gets BM25 alone. wait=True blocks instead (start-up thread, scripts).
    """
    if _State.loaded:
        return _State.retriever
    if not _State.lock.acquire(blocking=wait):
        return None
    try:
        if not _State.loaded:
            _State.retriever = _open()
            _State.loaded = True
        return _State.retriever
    finally:
        _State.lock.release()


def _open():
    m = mode()
    if m in ("0", "off", "false", "no"):
        _State.reason = "off"
        return None
    path = index_dir()
    if not (path / "index.faiss").exists():
        _State.reason = "no index (run scripts/build_embeddings.py)"
        (log.warning if m == "1" else log.info)("semantic search off: %s", _State.reason)
        return None
    try:
        from langchain_community.vectorstores import FAISS
        from langchain_community.vectorstores.utils import DistanceStrategy

        corpus = get_corpus()
        stamp = json.loads((path / "stamp.json").read_text(encoding="utf-8")) if (path / "stamp.json").exists() else {}
        if {k: stamp.get(k) for k in ("model", "files")} != {k: v for k, v in _stamp(corpus).items() if k != "passages"}:
            log.warning("the vector index was built from a different corpus; rebuild it with scripts/build_embeddings.py")
        emb = _embeddings_class()(model_name(), batch_size=16)
        # the index is our own file (built by scripts/build_embeddings.py), so loading its docstore is safe
        store = FAISS.load_local(str(path), emb, allow_dangerous_deserialization=True,
                                 distance_strategy=DistanceStrategy.MAX_INNER_PRODUCT)
        Lexical, Dense, Hybrid = _retriever_classes()
        retriever = Hybrid(lexical=Lexical(corpus=corpus), dense=Dense(store=store, corpus=corpus))
        _State.reason = f"on ({model_name()}, {emb.device})"
        log.info("semantic search %s", _State.reason)
        return retriever
    except Exception as exc:  # noqa: BLE001 - missing packages or a broken index: BM25 still works
        _State.reason = f"unavailable: {exc.__class__.__name__}: {exc}"[:200]
        (log.warning if m == "1" else log.info)("semantic search off: %s", _State.reason)
        return None


def warm_up() -> None:
    """Load the model off the request path (called from a background thread at start-up)."""
    try:
        _load(wait=True)
    except Exception:  # noqa: BLE001
        log.exception("semantic search warm-up failed")


def status() -> str:
    return _State.reason if _State.loaded else "loading"


def search(queries: list[str], k: int = 30) -> tuple[list[tuple[str, float, float]], dict[str, float], str]:
    """Ranked (passage_id, score, bm25_coverage), the dense similarity per id, and which retriever ran.

    With the hybrid retriever the score is the fused reciprocal-rank score; otherwise it is BM25.
    """
    corpus = get_corpus()
    queries = [q.strip().replace("\n", " ") for q in queries if q and q.strip()]
    retriever = _load()
    if retriever is None:
        return corpus.index.search(queries, k=k), {}, "bm25"
    docs = retriever.invoke("\n".join(dict.fromkeys(queries)))[:k]
    dense = {d.metadata["pid"]: round(d.metadata["dense"], 3) for d in docs if "dense" in d.metadata}
    return [(d.metadata["pid"], d.metadata["rrf"], d.metadata.get("coverage", 0.0)) for d in docs], dense, "hybrid"
