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
import re
import threading
import time
from collections import Counter

from ...core import timing
from ...core.textnorm import tokens

log = logging.getLogger("sabeeli.videos")

TITLE, TOPIC, DESC = 3.0, 2.0, 1.0
DESC_CHARS = 300          # the start of a description says what the video is about; the rest is often boilerplate
MIN_SCORE = 8.0           # a rare word in the title, or several in title and topic ("الرسول" alone suggested a
                          # video on insults to the Prophet for «من هو النبي محمد؟»)
# Which videos are close enough to suggest. Precision first: no video is better than an unrelated one.
# Checked by hand on 30 questions against the real ar/en lists: a video on the question scores >= 0.85
# in meaning AND shares most of the question's words in its title or topic; meaning alone let in
# "Why do Muslims do Hajj?" for a question about tawaf, words alone "Pillars of Faith" for the
# pillars of Islam. Both must agree.
MEANING = 0.85
COVERAGE = 0.45           # share of the question's words (idf-weighted; words no video uses count fully)
# Without the encoder, words alone must be much stronger.
WORDS_ONLY_SCORE, WORDS_ONLY_COVERAGE = 10.0, 0.6
# When the person asks for a video ("I want a video showing me how to pray", «أريد مقطعاً عن الصلاة»), the
# request words are left out of the match and the bars are a little lower: a close video is the answer.
VIDEO_REQUEST = re.compile(
    r"\b(videos?|clips?|watch|show(ing)? me|youtube|i want|i would like|i'?d like|can you|please|give me|find me)\b"
    r"|(فيديو|فديو|مقطع|مقاطع|مقطعا|مقطعاً|مرئي|مرئيات|أشاهد|اشاهد|شاهد|أرني|ارني|وريني|أريد|اريد|ابغى|أبغى|يشرح|يوضح)",
    re.I)
REQUESTED_MEANING, REQUESTED_COVERAGE = 0.83, 0.3


def wants_video(question: str) -> bool:
    return bool(re.search(r"\b(videos?|clips?|watch|youtube)\b|فيديو|فديو|مقطع|مقاطع|مرئي|أشاهد|اشاهد", question or "", re.I))
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
        t0 = time.perf_counter()
        try:
            import numpy as np
            st.vectors = np.asarray(enc.embed_documents([video_text(it) for it in st.items]), dtype="float32")
            log.info("videos: embedded %d videos for related suggestions in %.1fs", len(st.items), time.perf_counter() - t0)
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


def _word_ranking(st: _Stats, q_toks: set[str], h_toks: set[str]) -> list[tuple[int, float, float]]:
    """(video index, score, coverage) for videos sharing a meaningful title/topic word with the question.

    coverage is the larger of: the share of the question's own words the video has (a word no video
    uses counts at full rarity, so a question about something the list lacks stays low), and the share
    of the search phrases' known words (the analysis' rewording of the question)."""
    max_idf = math.log(1 + len(st.items))
    q_total = sum(st.idf.get(t, max_idf) for t in q_toks)
    h_known = {t for t in h_toks if t in st.idf}
    h_total = sum(st.idf[t] for t in h_known)
    if not q_total and not h_total:
        return []
    out = []
    for i, fields in enumerate(st.fields):
        score = q_cov = h_cov = 0.0
        anchored = False
        for t in q_toks | h_known:
            fw = fields.get(t)
            if fw is None:
                continue
            w = 1.0 if t in q_toks else 0.6
            score += st.idf[t] * fw * w
            if t in q_toks:
                q_cov += st.idf[t]
            if t in h_known:
                h_cov += st.idf[t]
            anchored = anchored or fw >= TOPIC
        coverage = max(q_cov / q_total if q_total else 0.0, h_cov / h_total if h_total else 0.0)
        if anchored and score >= MIN_SCORE:
            out.append((i, score, coverage))
    out.sort(key=lambda x: (x[1], x[2], st.items[x[0]].get("added") or 0), reverse=True)
    return out


def _similarities(st: _Stats, enc, texts: list[str]):
    """E5 similarity of every video to the question (best over the question and its search phrases)."""
    import numpy as np

    with timing.step("video_embed_query"):
        q = np.asarray([enc.embed_query(t) for t in texts if t.strip()], dtype="float32")
    with timing.step("video_similarity"):
        return (st.vectors @ q.T).max(axis=1) if len(q) else None


def related(idx, question: str, hints: list[str] | None = None, k: int = 3, encoder=None) -> list[dict]:
    """The k videos of this language most related to the question, best first; [] when none is close."""
    st = _stats(idx)
    requested = wants_video(question)
    if requested:      # match on the topic, not on "I want a video showing me"
        question = re.sub(r"\s+", " ", VIDEO_REQUEST.sub(" ", question)).strip() or question
    q_toks = set(tokens(question))
    h_toks = set(tokens(" ".join(hints or []))) - q_toks
    if pending(idx, encoder):
        return []    # meaning is on the way: better nothing for a few seconds than word-only guesses
    with timing.step("video_words"):
        words = _word_ranking(st, q_toks, h_toks)
    sims = _similarities(st, encoder, [question, " ".join(hints or [])]) if encoder is not None else None
    meaning_bar, coverage_bar = (REQUESTED_MEANING, REQUESTED_COVERAGE) if requested else (MEANING, COVERAGE)
    if sims is None:   # words only: keep strong matches
        words = [w for w in words if w[1] >= WORDS_ONLY_SCORE and w[2] >= WORDS_ONLY_COVERAGE]
        meaning: list[tuple[int, float]] = []
    else:              # both must agree: close in meaning, and most of the question's words in title/topic
        words = [w for w in words if w[2] >= coverage_bar and sims[w[0]] >= meaning_bar]
        meaning = sorted(((i, float(sims[i])) for i, *_ in words), key=lambda x: -x[1])
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
