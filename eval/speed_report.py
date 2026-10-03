"""Where the time goes: every step of answering, over many questions. Owner: Mushari.

Runs questions through the running app (/api/ask, then /api/videos/related like the Ask page does) and
prints, per step, the median, 90th percentile and worst time, its share of the total, and each model
provider's speed. The last line names the bottleneck.

The server also logs one line per question ("sabeeli.timing"), so a slow answer in a demo can be read
straight from the log.

Usage:  python -m uvicorn backend.app.main:app --port 8765   (in another terminal)
        python eval/speed_report.py [--base http://localhost:8765] [--rounds 1] [out.json]
Costs: two model calls per question (the 30 questions: well under one cent with Gemma 4 31B).
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from display_audit import QUESTIONS  # noqa: E402  (the same 30 synthetic questions)


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def pct(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, int(round(p * (len(values) - 1))))] if values else 0.0


def main() -> None:
    base = arg("--base", "http://localhost:8765")
    rounds = int(arg("--rounds", "1"))
    c = httpx.Client(base_url=base, timeout=180)
    token = c.post("/api/session").json()["token"]
    steps: dict[str, list[float]] = defaultdict(list)
    llm: dict[str, list[dict]] = defaultdict(list)
    totals, walls, videos = [], [], []
    rows = []
    for _ in range(rounds):
        for lang, q in QUESTIONS:
            t0 = time.perf_counter()
            d = c.post("/api/ask", data={"question": q, "lang": lang}, headers={"X-Seeker": token}).json()
            wall = (time.perf_counter() - t0) * 1000
            tm = d.get("trace", {}).get("timings", {})
            for name, ms in (tm.get("steps_ms") or {}).items():
                steps[name].append(ms)
            for call in tm.get("llm") or []:
                llm[call.get("provider") or "?"].append(call)
            totals.append((tm.get("total") or 0) * 1000)
            walls.append(wall)
            a = d.get("trace", {}).get("analysis") or {}
            hints = (a.get("queries_ar") or []) + (a.get("queries_en") or [])
            t1 = time.perf_counter()
            v = c.post("/api/videos/related", json={"lang": d.get("lang", "ar"), "q": q, "hints": hints}).json()
            videos.append((time.perf_counter() - t1) * 1000)
            rows.append({"q": q, "kind": d.get("kind"), "wall_ms": round(wall), "timings": tm,
                         "videos_ms": round(videos[-1]), "videos_state": v.get("state")})
            print(f"{wall / 1000:5.1f}s  {d.get('kind', '?'):9s} {q[:60]}")

    print(f"\n{len(totals)} questions | total per question: median {statistics.median(totals) / 1000:.2f}s, "
          f"p90 {pct(totals, .9) / 1000:.2f}s, worst {max(totals) / 1000:.2f}s "
          f"(round trip incl. HTTP: median {statistics.median(walls) / 1000:.2f}s)")
    print(f"\n{'step':18s} {'runs':>5s} {'median':>9s} {'p90':>9s} {'worst':>9s} {'share':>7s}")
    med_total = statistics.median(totals) or 1
    top = ("", 0.0)
    for name, vals in sorted(steps.items(), key=lambda kv: -statistics.median(kv[1])):
        med = statistics.median(vals)
        nested = name in ("bm25", "embed_query", "faiss", "fusion")   # parts of "retrieve"
        share = "" if nested else f"{med / med_total:6.0%}"
        if not nested and med > top[1]:
            top = (name, med)
        print(f"{('  ' if nested else '') + name:18s} {len(vals):5d} {med:8.0f}ms {pct(vals, .9):8.0f}ms {max(vals):8.0f}ms {share:>7s}")
    print(f"{'related videos':18s} {len(videos):5d} {statistics.median(videos):8.0f}ms {pct(videos, .9):8.0f}ms "
          f"{max(videos):8.0f}ms   (separate request, after the answer)")

    if llm:
        print(f"\n{'model provider':18s} {'calls':>5s} {'median s':>9s} {'worst s':>8s} {'tok/s':>7s} {'out tok':>8s}")
        for prov, calls in sorted(llm.items(), key=lambda kv: -len(kv[1])):
            secs = [x["s"] for x in calls]
            speed = [x["tok_s"] for x in calls if x.get("tok_s")]
            out = [x["out"] for x in calls if x.get("out")]
            print(f"{prov[:18]:18s} {len(calls):5d} {statistics.median(secs):9.2f} {max(secs):8.2f} "
                  f"{(statistics.median(speed) if speed else 0):7.0f} {(statistics.median(out) if out else 0):8.0f}")
    if top[0]:
        print(f"\nBottleneck: {top[0]} ({top[1] / 1000:.2f}s median, {top[1] / med_total:.0%} of an answer)")

    out_path = next((a for a in sys.argv[1:] if a.endswith(".json")), "speed_report.json")
    Path(out_path).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
