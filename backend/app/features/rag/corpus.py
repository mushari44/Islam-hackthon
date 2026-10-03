"""The approved corpus (Quran, hadith, glossary, Q&A encyclopedias, Bayyinat) and a BM25 index over it.

Everything the assistant may say about religion has to come from a Passage in
this module. Passages render their own display cards, so scripture shown to
the user is always the stored reference text, never model output.
"""
from __future__ import annotations

import json
import logging
import math
import pickle
import re
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from ...core.config import settings
from ...core.textnorm import normalize_ar, tokens

log = logging.getLogger("sabeeli.corpus")

INDEX_VERSION = 6
PREFIX = {"quran": "q", "hadith": "h", "term": "t", "qa": "qa", "bayyinat": "b"}
ANSWER_KINDS = ("qa", "bayyinat")  # whole approved answers to a question, with verses inside as markers
QA_CONTEXT_CHARS = 4000  # long answers are cut here for the model (the card shows all of it)
MARKER_IN_TEXT = re.compile(r"\[\[(q:\d{1,3}:\d{1,3})\]\]")


@dataclass
class Passage:
    id: str
    kind: str  # "quran" | "hadith" | "term" | "qa" | "bayyinat"
    data: dict = field(repr=False)

    # ---- labels ---------------------------------------------------------
    def title(self, lang: str) -> str:
        d = self.data
        if self.kind == "quran":
            if lang == "ar":
                return f"سورة {d['sura_name_ar']} ({d['sura']}:{d['aya']})"
            return f"Quran {d['sura']}:{d['aya']} ({d['sura_name_en']})"
        if self.kind == "hadith":
            t = d["title_ar"] if lang == "ar" or not d.get("title_en") else d["title_en"]
            return (f"حديث: {t}" if lang == "ar" else f"Hadith: {t}")[:160]
        if self.kind == "qa":
            return (f"سؤال وجواب: {d['title']}" if lang == "ar" else f"Q&A: {d['title']}")[:160]
        if self.kind == "bayyinat":
            return (f"بيّنات: {d['title']}" if lang == "ar" else f"Bayyinat: {d['title']}")[:160]
        return f"مصطلح: {d['ar']}" if lang == "ar" else f"Term: {d['en']}"

    def url(self, lang: str) -> str:
        d = self.data
        if self.kind == "term":
            return ""
        if self.kind in ANSWER_KINDS:
            return d["url_ar"]  # published in Arabic only
        return d["url_ar"] if lang == "ar" else d["url_en"]

    def source_label(self, lang: str) -> str:
        if self.kind == "quran":
            return ("نص المصحف من مجمع الملك فهد، والتفسير الميسر، عبر موسوعة القرآن الكريم (QuranEnc)"
                    if lang == "ar" else
                    "Mushaf text (King Fahd Complex) and Rowwad translation via QuranEnc")
        if self.kind == "hadith":
            return ("موسوعة الأحاديث النبوية (HadeethEnc)" if lang == "ar"
                    else "Encyclopedia of Translated Prophetic Hadiths (HadeethEnc)")
        if self.kind == "qa":
            return (f"{self.data['enc_ar']}، جمعية خدمة المحتوى الإسلامي باللغات (icadb)" if lang == "ar"
                    else f"{self.data['enc_en']}, Islamic Content Service Association (icadb), in Arabic")
        if self.kind == "bayyinat":
            d = self.data
            return (f"«بينات: أسئلة وأجوبة عن الإسلام»، مركز أصول، المسألة {d['n']} (ص {d['page']})" if lang == "ar"
                    else f"“Bayyinat: Questions and Answers about Islam”, Osoul Center, in Arabic, question {d['n']} (p. {d['page']})")
        return glossary_source(lang)

    # ---- model context --------------------------------------------------
    def context_blocks(self, lang: str, focus: set[str] | None = None, full: bool = False) -> list[str]:
        """Text blocks given to Claude as one search result (each block is citable).

        focus: search tokens of the question; a long Q&A or Bayyinat answer then keeps the lines that
        match them best instead of only its beginning. full: every line, no length budget.
        """
        d = self.data
        if self.kind == "quran":
            blocks = [f"[Quran {d['sura']}:{d['aya']}] Reference Arabic text (display only, do not reproduce): {d['text_ar']}",
                      f"التفسير الميسر: {d['tafsir_ar']}"]
            if lang != "ar":
                blocks.append(f"English translation of the meaning (Rowwad): {d['translation_en']}")
            return blocks
        if self.kind == "hadith":
            if lang == "ar":
                return [f"[Hadith {d['hid']}] {d['text_ar']} ({d['attribution_ar']}، درجة الحديث: {d['grade_ar']})",
                        f"الشرح: {d['explanation_ar']}",
                        "من فوائد الحديث: " + " ".join(d.get("hints_ar") or [])]
            return [f"[Hadith {d['hid']}] {d['text_en'] or d['text_ar']} (Attribution: {d['attribution_en'] or d['attribution_ar']}; grade: {d['grade_en'] or d['grade_ar']})",
                    f"Explanation: {d['explanation_en'] or d['explanation_ar']}",
                    "Lessons: " + " ".join(d.get("hints_en") or d.get("hints_ar") or [])]
        if self.kind == "qa":
            return self._answer_blocks([f"[Q&A {self.id}, {d['enc_en']}] السؤال: {d['question']}"], d["answer"],
                                       focus, full)
        if self.kind == "bayyinat":
            head = [f"[Bayyinat {self.id}] المسألة: {d['title']}", f"السؤال: {d['question']}"]
            if d.get("similar"):
                head.append("عبارات مشابهة للسؤال: " + " / ".join(d["similar"]))
            head += ["مختصر الإجابة:"] + [x.strip() for x in d["short_answer"].split("\n") if x.strip()]
            return self._answer_blocks(head, "الجواب التفصيلي:\n" + d["answer"], focus, full)
        return [f"Approved term: {d['ar']} = {d['en']}. Usage rule: {d['rule_ar']}"]

    @staticmethod
    def _answer_blocks(head: list[str], answer: str, focus: set[str] | None = None, full: bool = False) -> list[str]:
        """The question, then the answer line by line (each line citable), within QA_CONTEXT_CHARS.

        A long answer keeps its opening lines (where the answer is usually stated), then the lines
        that share the most words with the question, in their original order; "(…)" marks a gap.
        Verses inside the answer are already [[q:..]] markers pointing at the Mushaf, so the model
        can show them the same way it shows any verse.
        """
        lines = [x.strip() for x in answer.split("\n") if x.strip()]
        if full or sum(len(x) for x in lines) <= QA_CONTEXT_CHARS:
            return list(head) + lines
        keep: set[int] = set()
        used = 0
        for i in range(min(3, len(lines))):  # the opening lines
            if used + len(lines[i]) <= QA_CONTEXT_CHARS:
                keep.add(i)
                used += len(lines[i])
        if focus:
            ranked = sorted(range(len(lines)), key=lambda i: (-len(focus & set(tokens(lines[i]))), i))
        else:
            ranked = list(range(len(lines)))
        for i in ranked:
            if i not in keep and used + len(lines[i]) <= QA_CONTEXT_CHARS:
                keep.add(i)
                used += len(lines[i])
        blocks, last = list(head), -1
        for i in sorted(keep):
            if i != last + 1:
                blocks.append("(…)")
            blocks.append(lines[i])
            last = i
        if last != len(lines) - 1:
            blocks.append("(…)")
        return blocks

    def verse_refs(self) -> list[str]:
        """Mushaf verse ids this passage points to (the verses inside a Q&A answer)."""
        return list(self.data.get("refs") or []) if self.kind in ANSWER_KINDS else []

    # ---- display card ---------------------------------------------------
    def card(self, lang: str) -> dict:
        d = self.data
        base = {"id": self.id, "kind": self.kind, "title": self.title(lang),
                "url": self.url(lang), "source": self.source_label(lang)}
        if self.kind == "quran":
            base.update({"sura": d["sura"], "aya": d["aya"], "text_ar": d["text_ar"],
                         "tafsir_ar": d["tafsir_ar"], "translation_en": d["translation_en"],
                         "sura_name_ar": d["sura_name_ar"], "sura_name_en": d["sura_name_en"]})
        elif self.kind == "hadith":
            base.update({"text_ar": d["text_ar"], "text_en": d.get("text_en", ""),
                         "grade": d["grade_ar"] if lang == "ar" else (d.get("grade_en") or d["grade_ar"]),
                         "attribution": d["attribution_ar"] if lang == "ar" else (d.get("attribution_en") or d["attribution_ar"]),
                         "explanation": d["explanation_ar"] if lang == "ar" else (d.get("explanation_en") or d["explanation_ar"])})
        elif self.kind in ANSWER_KINDS:
            corpus = get_corpus()
            verses = {}
            for vid in self.verse_refs():
                v = corpus.get(vid)
                if v:
                    verses[vid] = {k: v.data[k] for k in ("sura", "aya", "text_ar", "translation_en", "sura_name_ar", "sura_name_en")}
            base.update({"question": d["question"], "answer": d["answer"], "verses": verses})
            if self.kind == "qa":
                base.update({"categories": d.get("categories") or [],
                             "encyclopedia": d["enc_ar"] if lang == "ar" else d["enc_en"]})
            else:
                base.update({"heading": d["title"], "short_answer": d["short_answer"], "section": d.get("section", "")})
        else:
            base.update({"term_ar": d["ar"], "term_en": d["en"], "rule_ar": d["rule_ar"]})
        return base

    def search_text(self) -> str:
        d = self.data
        if self.kind == "quran":
            # The tafsir carries most of the plain-language vocabulary people search with.
            return " ".join([d["text_ar"], d["tafsir_ar"], d["translation_en"], d["sura_name_ar"], d["sura_name_en"]])
        if self.kind == "hadith":
            return " ".join([d["title_ar"], d["title_ar"], d["text_ar"], d["explanation_ar"], " ".join(d.get("hints_ar") or []),
                             d.get("title_en", ""), d.get("title_en", ""), d.get("text_en", ""), d.get("explanation_en", ""),
                             " ".join(d.get("hints_en") or [])])
        if self.kind == "qa":
            answer = MARKER_IN_TEXT.sub(" ", d["answer"])
            return " ".join([d["title"], d["title"], d["question"], answer, " ".join(d.get("categories") or [])])
        if self.kind == "bayyinat":
            similar = " ".join(d.get("similar") or [])
            text = " ".join([d["gist"], d["short_answer"], d["answer"]])
            return " ".join([d["title"], d["title"], d["question"], similar, similar, MARKER_IN_TEXT.sub(" ", text)])
        return " ".join([d["ar"], d["en"], " ".join(d.get("aliases") or []), d["rule_ar"]] * 2)


# ---------------------------------------------------------------------------

def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@lru_cache(maxsize=1)
def _glossary() -> dict:
    path = settings.corpus_dir / "glossary.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"terms": [], "source": {}}


def glossary_source(lang: str) -> str:
    return _glossary().get("source", {}).get("ar" if lang == "ar" else "en", "")


class Corpus:
    def __init__(self) -> None:
        t0 = time.perf_counter()
        self.passages: dict[str, Passage] = {}
        self.order: list[str] = []
        for row in _read_jsonl(settings.corpus_dir / "quran.jsonl"):
            self._add(Passage(row["id"], "quran", row))
        for row in _read_jsonl(settings.corpus_dir / "hadith.jsonl"):
            self._add(Passage(row["id"], "hadith", row))
        for term in _glossary().get("terms", []):
            self._add(Passage(f"t:{term['key']}", "term", term))
        for row in _read_jsonl(settings.corpus_dir / "qa.jsonl"):
            self._add(Passage(row["id"], "qa", row))
        # built locally by scripts/ingest_bayyinat.py (the book's rights are reserved, so it isn't in git)
        for row in _read_jsonl(settings.corpus_dir / "bayyinat.jsonl"):
            self._add(Passage(row["id"], "bayyinat", row))
        t1 = time.perf_counter()
        self.index = BM25Index.load_or_build(self)
        log.info("corpus: %d passages read in %.1fs, BM25 index ready in %.1fs", len(self.order), t1 - t0,
                 time.perf_counter() - t1)

    def _add(self, p: Passage) -> None:
        self.passages[p.id] = p
        self.order.append(p.id)

    def get(self, pid: str) -> Passage | None:
        return self.passages.get(pid)

    def verse(self, sura: int, aya: int) -> Passage | None:
        return self.passages.get(f"q:{sura}:{aya}")

    def stats(self) -> dict:
        c = Counter(p.kind for p in self.passages.values())
        return {"quran_verses": c.get("quran", 0), "hadiths": c.get("hadith", 0), "terms": c.get("term", 0),
                "qa": c.get("qa", 0), "bayyinat": c.get("bayyinat", 0)}

    def find_terms(self, text: str) -> list[Passage]:
        """Glossary entries mentioned in a text (by Arabic form, English form or alias)."""
        norm = normalize_ar(text).lower()
        found = []
        for term in _glossary().get("terms", []):
            forms = [term["ar"], term["en"], *term.get("aliases", [])]
            for form in forms:
                f = normalize_ar(form).lower()
                if f and re.search(rf"(?<![\w]){re.escape(f)}(?![\w])", norm):
                    found.append(self.passages[f"t:{term['key']}"])
                    break
        return found


class BM25Index:
    K1 = 1.4
    B = 0.75

    def __init__(self, ids: list[str], postings: dict[str, list[tuple[int, int]]], lengths: list[int]):
        self.ids = ids
        self.postings = postings
        self.lengths = lengths
        self.avg_len = (sum(lengths) / len(lengths)) if lengths else 1.0
        n = len(ids)
        self.idf = {t: math.log(1 + (n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in postings.items()}

    @classmethod
    def build(cls, corpus: Corpus) -> "BM25Index":
        postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        lengths = []
        for i, pid in enumerate(corpus.order):
            toks = tokens(corpus.passages[pid].search_text())
            lengths.append(len(toks))
            for t, tf in Counter(toks).items():
                postings[t].append((i, tf))
        return cls(list(corpus.order), dict(postings), lengths)

    @classmethod
    def load_or_build(cls, corpus: Corpus) -> "BM25Index":
        cache = settings.data_dir / "cache" / "bm25.pkl"
        sources = [settings.corpus_dir / n for n in ("quran.jsonl", "hadith.jsonl", "glossary.json", "qa.jsonl", "bayyinat.jsonl")]
        stamp = [INDEX_VERSION] + [(p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in sources if p.exists()]
        if cache.exists():
            try:
                with cache.open("rb") as f:
                    saved = pickle.load(f)
                if saved.get("stamp") == stamp and saved["ids"] == corpus.order:
                    return cls(saved["ids"], saved["postings"], saved["lengths"])
            except Exception:  # noqa: BLE001 - a stale or corrupt cache is simply rebuilt
                pass
        index = cls.build(corpus)
        cache.parent.mkdir(parents=True, exist_ok=True)
        with cache.open("wb") as f:
            pickle.dump({"stamp": stamp, "ids": index.ids, "postings": index.postings, "lengths": index.lengths}, f)
        return index

    def search(self, queries: list[str], k: int = 10, kinds: set[str] | None = None) -> list[tuple[str, float, float]]:
        """Return (passage_id, score, coverage) for the best k passages.

        coverage is the share of distinct query terms (weighted by idf) that the
        passage contains; the pipeline uses it to decide whether the sources are
        enough to answer at all.
        """
        q_terms: Counter = Counter()
        for q in queries:
            q_terms.update(set(tokens(q)))
        if not q_terms:
            return []
        scores: dict[int, float] = defaultdict(float)
        matched: dict[int, float] = defaultdict(float)
        # A query term found nowhere in the corpus is the strongest sign the sources
        # can't answer, so it counts against coverage with the highest possible idf.
        max_idf = math.log(1 + len(self.ids))
        total_idf = sum(self.idf.get(t, max_idf) for t in q_terms) or 1.0
        for term, qtf in q_terms.items():
            plist = self.postings.get(term)
            if not plist:
                continue
            idf = self.idf[term]
            for doc, tf in plist:
                denom = tf + self.K1 * (1 - self.B + self.B * self.lengths[doc] / self.avg_len)
                scores[doc] += idf * (tf * (self.K1 + 1) / denom) * (1 + 0.25 * (qtf - 1))
                matched[doc] += idf
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        prefixes = {PREFIX[k_] for k_ in kinds} if kinds else None
        out = []
        for doc, score in ranked:
            pid = self.ids[doc]
            if prefixes and pid.split(":", 1)[0] not in prefixes:
                continue
            out.append((pid, score, min(1.0, matched[doc] / total_idf)))
            if len(out) >= k:
                break
        return out

    def unknown_terms(self, text: str) -> list[str]:
        """Query terms that appear nowhere in the corpus (a sign the sources can't answer)."""
        return [t for t in set(tokens(text)) if t not in self.postings]


_lock = threading.Lock()
_corpus: Corpus | None = None


def get_corpus() -> Corpus:
    """Built once per process (the start-up warm-up thread and early requests share it)."""
    global _corpus
    if _corpus is None:
        with _lock:
            if _corpus is None:
                _corpus = Corpus()
                from .embeddings import mode, warm_up
                if mode() not in ("0", "off", "false", "no"):
                    threading.Thread(target=warm_up, daemon=True).start()  # load E5 off the request path
    return _corpus
