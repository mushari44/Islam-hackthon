"""Videos related to a question asked on the Ask page. Owner: Mushari.

A question is a sentence ("لماذا يصوم المسلمون شهرا كاملا؟"), not the few words the videos page's
search expects, so not every word can be required. Two signals, fused like RAG search (70% meaning,
30% words, by reciprocal rank):

  * words  - each video's own published text scored BM25-style: a word in the title counts most,
             then the topic, then the start of the description, each weighted by how rare it is
             among that language's videos. A video must share a meaningful word with the question
             in its title or topic.
  * meaning - when RAG's multilingual E5 encoder is loaded (rag/public.py), every video's title,
             topic and description start are embedded once per index build, in the background,
             and compared with the question. Arabic "يصوم" then meets "الصيام" and "Ramadan".

The answer's search phrases (from the RAG analysis, Arabic and English) can be passed as hints: they
bring the usual terms ("الكعبة" -> "القبلة") without reading or rewriting any video text. Nothing here
generates or summarises video text, and suggestions are never cited in the answer (CLAUDE.md).
"""
from __future__ import annotations

import logging
import math
import threading
from collections import Counter

from ...core.textnorm import tokens

log = logging.getLogger("sabeeli.videos")

TITLE, TOPIC, DESC = 3.0, 2.0, 1.0
DESC_CHARS = 300          # the start of a description says what the video is about; the rest is often boilerplate
MIN_COVERAGE = 0.3        # share of the question's known words (idf-weighted) a word match must contain
MIN_SCORE = 4.0           # roughly: one rare word in the title, or several common ones
# Which videos are close enough to suggest. E5 scores short titles in a narrow band (checked by hand
# on 12 questions against the real ar/en lists): a clear match scores >= 0.85; 0.815-0.85 is either a
# match or a video that merely shares a common word, so there the words must agree too.
STRONG_MEANING = 0.85
WEAK_MEANING = 0.815
# Without the encoder, words alone must be much stronger ("مسلم" or "يوم" alone suggests nothing).
WORDS_ONLY_SCORE, WORDS_ONLY_COVERAGE = 10.0, 0.5
DENSE_WEIGHT = 0.7        # same split as RAG search
RRF_C = 60

_lock = threading.Lock()


def video_text(it: dict) -> str:
    return " - ".join(x for x in (it.get("title", ""), it.get("topic") or "", (it.get("description") or "")[:DESC_CHARS]) if x)


class _Stats:
    """Per-video word weights and per-word rarity for one built index (rebuilt when the index is)."""

    def __init__(self, items: list[dict]):
        self.items = items
        self.fields: list[dict[str, float]] = []
        df: Counter = Counter()
        for it in items:
            weights: dict[str, float] = {}
            for text, w in (((it.get("description") or "")[:DESC_CHARS], DESC), (it.get("topic") or "", TOPIC),
                            (it.get("title", ""), TITLE)):
                for tok in set(tokens(text)):
                    weights[tok] = max(weights.get(tok, 0.0), w)
            self.fields.append(weights)
            df.update(weights.keys())
        n = len(items) or 1
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.vectors = None          # numpy array (n, dim) once embedded
        self.embedding = False


def _stats(idx) -> _Stats:
    cached = getattr(idx, "_related_stats", None)
    if cached is not None and cached[0] == idx.built_at:
        return cached[1]
    with _lock:
        cached = getattr(idx, "_related_stats", None)
        if cached is None or cached[0] != idx.built_at:
            idx._related_stats = (idx.built_at, _Stats(idx.items))
        return idx._related_stats[1]


def _embed_in_background(st: _Stats, enc) -> None:
    """Embed every video of the index once; until it finishes, suggestions use words only."""
    if st.vectors is not None or st.embedding:
        return
    st.embedding = True

    def run():
        try:
            import numpy as np
            st.vectors = np.asarray(enc.embed_documents([video_text(it) for it in st.items]), dtype="float32")
            log.info("videos: embedded %d videos for related suggestions", len(st.items))
        except Exception:  # noqa: BLE001 - words still work
            log.exception("videos: embedding for related suggestions failed")
        finally:
            st.embedding = False

    threading.Thread(target=run, daemon=True).start()


def pending(idx, encoder) -> bool:
    """True while this index's videos are being embedded (the client asks again shortly)."""
    if encoder is None:
        return False
    st = _stats(idx)
    if st.vectors is None:
        _embed_in_background(st, encoder)
        return True
    return False


def prepare(get_index, get_encoder, langs=("ar", "en"), wait_s: float = 600.0) -> None:
    """At start-up: once the encoder and a language's video list are both ready, embed its videos, so the
    first question doesn't wait. Runs in a background thread; gives up quietly after wait_s."""
    import time

    def run():
        deadline = time.time() + wait_s
        todo = list(langs)
        while todo and time.time() < deadline:
            enc = get_encoder()
            for lang in list(todo):
                idx, state = get_index(lang)
                if enc is not None and idx is not None:
                    pending(idx, enc)
                    todo.remove(lang)
            time.sleep(5)

    threading.Thread(target=run, daemon=True).start()


def _word_ranking(st: _Stats, query: dict[str, float]) -> list[tuple[int, float, float]]:
    known = {t: w for t, w in query.items() if t in st.idf}   # a word no video uses can't tell videos apart
    total = sum(st.idf[t] * w for t, w in known.items())
    if not total:
        return []
    out = []
    for i, fields in enumerate(st.fields):
        score = covered = 0.0
        anchored = False
        for t, w in known.items():
            fw = fields.get(t)
            if fw is None:
                continue
            score += st.idf[t] * fw * w
            covered += st.idf[t] * w
            anchored = anchored or fw >= TOPIC
        if anchored and score >= MIN_SCORE and covered / total >= MIN_COVERAGE:
            out.append((i, score, covered / total))
    out.sort(key=lambda x: (x[1], x[2], st.items[x[0]].get("added") or 0), reverse=True)
    return out


def _similarities(st: _Stats, enc, texts: list[str]):
    """E5 similarity of every video to the question (best over the question and its search phrases)."""
    import numpy as np

    q = np.asarray([enc.embed_query(t) for t in texts if t.strip()], dtype="float32")
    return (st.vectors @ q.T).max(axis=1) if len(q) else None


def related(idx, question: str, hints: list[str] | None = None, k: int = 3, encoder=None) -> list[dict]:
    """The k videos of this language most related to the question, best first; [] when none is close."""
    st = _stats(idx)
    q_toks = set(tokens(question))
    h_toks = set(tokens(" ".join(hints or []))) - q_toks
    # words the question itself uses count fully; words that only the search phrases add count less
    query = {t: 1.0 for t in q_toks} | {t: 0.6 for t in h_toks}
    if pending(idx, encoder):
        return []    # meaning is on the way: better nothing for a few seconds than word-only guesses
    words = _word_ranking(st, query)
    sims = _similarities(st, encoder, [question, " ".join(hints or [])]) if encoder is not None else None
    if sims is None:   # words only: keep strong matches
        words = [w for w in words if w[1] >= WORDS_ONLY_SCORE and w[2] >= WORDS_ONLY_COVERAGE]
        meaning: list[tuple[int, float]] = []
    else:              # meaning decides; a borderline meaning needs the words to agree
        word_ids = {i for i, *_ in words}
        ok = {int(i) for i in (sims >= STRONG_MEANING).nonzero()[0]}
        ok |= {i for i in word_ids if sims[i] >= WEAK_MEANING}
        words = [w for w in words if w[0] in ok]
        meaning = sorted(((i, float(sims[i])) for i in ok), key=lambda x: -x[1])
    fused: dict[int, float] = {}
    for rank, (i, *_) in enumerate(words, start=1):
        fused[i] = fused.get(i, 0.0) + (1 - DENSE_WEIGHT if sims is not None else 1.0) / (RRF_C + rank)
    for rank, (i, _) in enumerate(meaning, start=1):
        fused[i] = fused.get(i, 0.0) + DENSE_WEIGHT / (RRF_C + rank)
    word_info = {i: (s, c) for i, s, c in words}
    sim = dict(meaning)
    out, seen_titles = [], set()
    for i, _ in sorted(fused.items(), key=lambda kv: (-kv[1], -(st.items[kv[0]].get("added") or 0))):
        it = st.items[i]
        key = " ".join(tokens(it["title"]))     # a series often repeats one title: suggest it once
        if key in seen_titles:
            continue
        seen_titles.add(key)
        s, c = word_info.get(i, (None, None))
        out.append({**it, "match": {"words": round(s, 2) if s else None, "coverage": round(c, 2) if c else None,
                                    "meaning": round(sim[i], 3) if i in sim else None}})
        if len(out) >= k:
            break
    return out
