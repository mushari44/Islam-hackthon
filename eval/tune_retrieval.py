"""Replay retrieval for the evaluation set under different settings, without the model (free). Owner: Mushari.

Uses the analyses (search phrases) saved by eval/run_eval.py, so every setting sees the same queries, and
reports for the cases with expected sources:
  hit@k   an expected passage is among the passages the model receives (the pipeline's retrieve());
  MRR     1 / rank of the first expected passage in the fused list (0 when it is not in the top 60).
Then, for the app's sources-only mode, what each SHOW_* setting would show: the right passage first,
something else, or nothing.

Usage:  python eval/tune_retrieval.py eval/results/<run>.json
"""
from __future__ import annotations

import csv
import json
import logging
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def any_id(expected: list[str], got: list[str]) -> bool:
    return any(g == e or (e.endswith("*") and g.startswith(e[:-1])) for e in expected for g in got)


def first_rank(expected: list[str], order: list[str]) -> int | None:
    for i, pid in enumerate(order, start=1):
        if any_id(expected, [pid]):
            return i
    return None


def main() -> None:
    logging.disable(logging.CRITICAL)
    from backend.app.features.rag import embeddings, pipeline

    results = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    analyses = {r["id"]: r["out"].get("trace", {}).get("analysis") for r in results["runs"]}
    cases = [c for c in csv.DictReader(open(ROOT / "eval" / "cases.csv", encoding="utf-8"))
             if c["expect_sources"] and not c["expect"].startswith("quote") and not c["photo"] and analyses.get(c["id"])]
    unanswerable = [c for c in csv.DictReader(open(ROOT / "eval" / "cases.csv", encoding="utf-8"))
                    if c["expect"].startswith("abstain") and analyses.get(c["id"])]
    retriever = embeddings._load(wait=True)

    def evaluate(label: str) -> None:
        hits, rr, misses = 0, [], []
        for c in cases:
            a = {**analyses[c["id"]]}
            a.setdefault("standalone_question", c["question"])
            expected = c["expect_sources"].split()
            chosen, _ = pipeline.retrieve(a, c["question"], [])
            ok = any_id(expected, [p.id for p in chosen])
            hits += ok
            queries = [a.get("standalone_question") or c["question"], c["question"]]
            queries += a.get("queries_ar", [])[:4] + a.get("queries_en", [])[:4] + a.get("terms", [])[:4]
            raw, _, _ = embeddings.search(queries, k=60)
            r = first_rank(expected, [pid for pid, _, _ in raw])
            rr.append(1 / r if r else 0.0)
            if not ok:
                misses.append(f"{c['id']}({r})")
        print(f"{label:34s} hit@k {hits}/{len(cases)}  MRR {statistics.mean(rr):.3f}  misses {' '.join(misses)}")

    print(f"{len(cases)} cases with expected sources; top_k={pipeline.settings.top_k}\n")
    slot_saved = pipeline.ANSWER_SLOT
    for slot in (None, 0.85, 0.84, 0.83):
        pipeline.ANSWER_SLOT = slot
        for w in (0.0, 0.3, 0.5, 0.7, 0.8, 1.0):
            if retriever is None:
                break
            retriever.weights = [1 - w, w]
            evaluate(f"answer slot {slot}, dense {w:.0%}")
        print()
    pipeline.ANSWER_SLOT = slot_saved
    if retriever is not None:
        retriever.weights = [1 - embeddings.dense_weight(), embeddings.dense_weight()]

    # Sources-only mode (no model): what would be shown at each bar
    print("\nsources-only display (first shown passage expected / something else / nothing; unanswerable: shown anything)")
    rows = {}
    for c in cases + unanswerable:
        a = {**analyses[c["id"]]}
        a.setdefault("standalone_question", c["question"])
        chosen, rtrace = pipeline.retrieve(a, c["question"], [])
        rows[c["id"]] = (c, chosen, rtrace)
    saved = (pipeline.SHOW_ANSWER, pipeline.SHOW_EXTRA, pipeline.SHOW_PASSAGE)
    for show_answer, show_passage in ((0.86, 0.85), (0.85, 0.85), (0.84, 0.85), (0.86, 0.86), (0.85, 0.86), (0.84, 0.84)):
        pipeline.SHOW_ANSWER, pipeline.SHOW_PASSAGE = show_answer, show_passage
        right = other = none = bad = 0
        wrong_ids = []
        for cid, (c, chosen, rtrace) in rows.items():
            segs = pipeline._sources_only(chosen, c["lang"], rtrace, c["question"])
            shown = [s["cites"][0] for s in segs if s["cites"] and not s["cites"][0].startswith("t:")]
            if c["expect"] == "abstain":
                bad += bool(shown)
                continue
            if not shown:
                none += 1
            elif any_id(c["expect_sources"].split(), shown[:1]):
                right += 1
            else:
                other += 1
                wrong_ids.append(f"{cid}:{shown[0]}")
        print(f"  answer>={show_answer} passage>={show_passage}: right {right}, other {other}, nothing {none}; "
              f"unanswerable shown {bad}/{len(unanswerable)}   other: {' '.join(wrong_ids)}")
    pipeline.SHOW_ANSWER, pipeline.SHOW_EXTRA, pipeline.SHOW_PASSAGE = saved


if __name__ == "__main__":
    main()
