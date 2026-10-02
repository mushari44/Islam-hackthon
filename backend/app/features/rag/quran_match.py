"""Match quoted or photographed Arabic text against the reference Mushaf text.

The matcher is deterministic:
  1. candidate verses come from a 4-gram index over alef-free letter skeletons,
     so Uthmani spelling (صلوٰة، ٱلرَّحۡمَٰنِ) and everyday spelling (صلاة، الرحمن)
     look the same;
  2. each candidate span (1-3 consecutive verses) is aligned word by word with
     the quote (the whole quote must align, the verse may start/end outside it);
  3. the alignment yields the differences: changed, missing and extra words.
A difference in alef alone (قل / قال) is reported too, unless the reference
word writes that long vowel with a dagger alef, the usual spelling split.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
import threading

from ...core.textnorm import ALEF, ARABIC_RE, DAGGER_ALEF, WORD_RE, normalize_ar, skeleton
from .corpus import Passage, get_corpus

GRAM = 4
MIN_SKELETON = 7


@dataclass
class VerseMatch:
    ids: list[str]            # one verse, or consecutive verses when the quote spans them
    score: float              # share of the quoted words found, in order, in the reference
    exact: bool               # no meaningful difference from the reference
    differences: list[dict]   # word-level differences (quoted vs. reference)
    ambiguous: bool = False   # the quote is short and fits several verses equally well

    def as_dict(self) -> dict:
        return {"ids": self.ids, "score": round(self.score, 3), "exact": self.exact,
                "differences": self.differences, "ambiguous": self.ambiguous}


def arabic_words(text: str) -> list[str]:
    return [w for w in WORD_RE.findall(text or "") if ARABIC_RE.search(w)]


def _sub_cost(a: str, b: str) -> float:
    if a == b or a.replace("ت", "ه") == b.replace("ت", "ه"):
        return 0.0  # identical, or ة / open ت (نعمة / نِعۡمَتَ)
    return 1.0


EXTRA = 1.0      # a quoted word that is not in the reference
GAP_OPEN = 1.0   # reference words left out of the quote...
GAP_EXT = 0.15   # ...cost little per extra word, so one omission reads as one omission


def align(q: list[str], r: list[str]) -> tuple[float, list[tuple[str, list[int], list[int]]]]:
    """Semi-global word alignment (Gotoh): all of q, any contiguous part of r.

    Ops: ("eq"|"sub", [qi], [rj]), ("extra", [qi], []), ("missing", [], [rj]),
    and merges ("eq", [qi, qi+1], [rj]) / ("eq", [qi], [rj, rj+1]) for
    word-splitting differences such as يا أيها / يَٰٓأَيُّهَا.
    """
    n, m = len(q), len(r)
    INF = float("inf")
    # cost[s][i][j] for states s = 0 (match), 1 (extra), 2 (missing); back holds (state, di, dj, tag, prev_state)
    cost = [[[INF] * (m + 1) for _ in range(n + 1)] for _ in range(3)]
    back = [[[None] * (m + 1) for _ in range(n + 1)] for _ in range(3)]
    for j in range(m + 1):
        cost[0][0][j] = 0.0  # the quote may start anywhere in the reference

    def best_at(i, j):
        s = min(range(3), key=lambda k: cost[k][i][j])
        return cost[s][i][j], s

    for i in range(0, n + 1):
        for j in range(0, m + 1):
            if i >= 1 and j >= 1:
                c0, s0 = best_at(i - 1, j - 1)
                sc = _sub_cost(q[i - 1], r[j - 1])
                cost[0][i][j], back[0][i][j] = c0 + sc, ("eq" if sc == 0 else "sub", 1, 1, s0)
                if i >= 2 and q[i - 2] + q[i - 1] == r[j - 1]:
                    c2, s2 = best_at(i - 2, j - 1)
                    if c2 < cost[0][i][j]:
                        cost[0][i][j], back[0][i][j] = c2, ("eq", 2, 1, s2)
                if j >= 2 and q[i - 1] == r[j - 2] + r[j - 1]:
                    c2, s2 = best_at(i - 1, j - 2)
                    if c2 < cost[0][i][j]:
                        cost[0][i][j], back[0][i][j] = c2, ("eq", 1, 2, s2)
            if i >= 1:
                c1, s1 = best_at(i - 1, j)
                cost[1][i][j], back[1][i][j] = c1 + EXTRA, ("extra", 1, 0, s1)
            if i >= 1 and j >= 1:
                opts = [(cost[0][i][j - 1] + GAP_OPEN, 0), (cost[2][i][j - 1] + GAP_EXT, 2), (cost[1][i][j - 1] + GAP_OPEN, 1)]
                c, s = min(opts)
                cost[2][i][j], back[2][i][j] = c, ("missing", 0, 1, s)

    # Prefer consuming the reference on ties, so a wrong last word reads as "changed".
    end_cost, end_j, end_s = min(((cost[s][n][j], -j, s) for j in range(m + 1) for s in (0, 1)))
    end_j = -end_j
    ops = []
    i, j, s = n, end_j, end_s
    while i > 0:
        tag, di, dj, prev = back[s][i][j]
        ops.append((tag, list(range(i - di, i)), list(range(j - dj, j))))
        i, j, s = i - di, j - dj, prev
    ops.reverse()
    return end_cost, ops


def _outside(ops) -> int:
    """Quoted words before the first / after the last aligned word (e.g. «قال تعالى»)."""
    aligned = [k for k, op in enumerate(ops) if op[0] in ("eq", "sub")]
    if not aligned:
        return 0
    return sum(len(qi) for k, (tag, qi, _) in enumerate(ops) if tag == "extra" and (k < aligned[0] or k > aligned[-1]))


class QuranMatcher:
    def __init__(self) -> None:
        corpus = get_corpus()
        self.verses: list[Passage] = [p for p in corpus.passages.values() if p.kind == "quran"]
        self.words = [arabic_words(p.data["text_ar"]) for p in self.verses]
        self.word_sk = [[skeleton(w) for w in ws] for ws in self.words]
        self.grams: dict[str, set[int]] = defaultdict(set)
        for i, sk in enumerate(self.word_sk):
            s = "".join(sk)
            for j in range(len(s) - GRAM + 1):
                self.grams[s[j:j + GRAM]].add(i)

    def _candidates(self, skel_in: str, limit: int = 40) -> list[int]:
        """Verses sharing the most (rarity-weighted) 4-grams with the quote; ties broken by position."""
        n = len(self.verses)
        scores: Counter = Counter()
        for g in {skel_in[j:j + GRAM] for j in range(len(skel_in) - GRAM + 1)}:
            hits = self.grams.get(g)
            if not hits:
                continue
            weight = math.log(1 + n / len(hits))
            for i in hits:
                scores[i] += weight
        return [i for i, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]

    def _span(self, start: int, length: int) -> list[int]:
        if start < 0:
            return []
        sura = self.verses[start].data["sura"]
        return [i for i in range(start, min(start + length, len(self.verses)))
                if self.verses[i].data["sura"] == sura]

    def match(self, text: str, max_results: int = 3) -> list[VerseMatch]:
        q_words = arabic_words(text)
        q_sk = [skeleton(w) for w in q_words]
        if len("".join(q_sk)) < MIN_SKELETON or len(q_words) < 2:
            return []
        q_set = Counter(q_sk)
        spans, seen = [], set()
        for i in self._candidates("".join(q_sk)):
            for start in (i - 2, i - 1, i):
                for length in (1, 2, 3):
                    idx = self._span(start, length)
                    if not idx or not (idx[0] <= i <= idx[-1]) or tuple(idx) in seen:
                        continue
                    seen.add(tuple(idx))
                    r_sk = [w for k in idx for w in self.word_sk[k]]
                    overlap = sum((q_set & Counter(r_sk)).values()) / len(q_sk)
                    spans.append((overlap, -len(idx), idx, r_sk))
        spans.sort(key=lambda x: (x[0], x[1]), reverse=True)

        results = []
        for overlap, _, idx, r_sk in spans[:12]:
            if overlap < 0.5:
                continue
            cost, ops = align(q_sk, r_sk)
            found = sum(len(qi) for tag, qi, _ in ops if tag == "eq")
            score = found / max(1, len(q_sk) - _outside(ops))
            results.append((-cost / len(q_sk), score, -len(idx), idx, ops))
        results.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)

        out: list[VerseMatch] = []
        used: set[int] = set()
        for _, score, _, idx, ops in results:
            if score < 0.6 or used & set(idx):
                continue
            used.update(idx)
            r_words = [w for k in idx for w in self.words[k]]
            diffs = self._differences(q_words, r_words, ops)
            out.append(VerseMatch(ids=[self.verses[k].id for k in idx], score=score,
                                  exact=not diffs and score == 1.0, differences=diffs))
            if len(out) >= max_results:
                break
        exact_hits = [m for m in out if m.exact]
        if len(exact_hits) > 1 or (len(out) > 1 and out[1].score >= out[0].score and len(q_words) <= 6):
            for m in out:
                m.ambiguous = True
        return out

    @staticmethod
    def _differences(q_words: list[str], r_words: list[str], ops) -> list[dict]:
        diffs: list[dict] = []
        first = next((k for k, op in enumerate(ops) if op[0] in ("eq", "sub")), 0)
        last = max((k for k, op in enumerate(ops) if op[0] in ("eq", "sub")), default=len(ops) - 1)
        for k, (tag, qi, rj) in enumerate(ops):
            if tag in ("missing", "extra") and (k < first or k > last):
                continue  # verse text outside the quoted part, or words around the quote
            if tag == "eq":
                if len(qi) == 1 and len(rj) == 1:
                    qw, rw = q_words[qi[0]], r_words[rj[0]]
                    qa, ra = normalize_ar(qw), normalize_ar(rw)
                    # Alef-only difference, not explained by a dagger alef in the reference.
                    if qa != ra and DAGGER_ALEF not in rw and qa.replace(ALEF, "") == ra.replace(ALEF, ""):
                        diffs.append({"type": "changed", "quoted": qw, "reference": rw})
                continue
            kind = {"sub": "changed", "extra": "extra", "missing": "missing"}[tag]
            item = {"type": kind,
                    "quoted": " ".join(q_words[x] for x in qi),
                    "reference": " ".join(r_words[x] for x in rj)}
            if diffs and diffs[-1]["type"] == kind == "missing":
                diffs[-1]["reference"] += " " + item["reference"]
            else:
                diffs.append(item)
        return diffs


_lock = threading.Lock()
_matcher: QuranMatcher | None = None


def get_matcher() -> QuranMatcher:
    global _matcher
    if _matcher is None:
        with _lock:
            if _matcher is None:
                _matcher = QuranMatcher()
    return _matcher


def looks_like_quote(text: str) -> bool:
    """A run of Arabic words long enough to be worth matching."""
    words = arabic_words(text)
    return len(words) >= 3 and len(skeleton(" ".join(words))) >= MIN_SKELETON


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, skeleton(a), skeleton(b), autojunk=False).ratio()
