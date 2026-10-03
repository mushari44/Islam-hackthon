"""Per-request step timings, so a slow answer shows which step was slow.

Each request runs in its own worker thread, so the collector is thread-local: a request calls start(),
code anywhere below it wraps work in step("name"), model clients call llm_call(...), and the request
reads current() at the end. Nothing is recorded when no request started a collector (scripts, tests).
"""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager

_local = threading.local()


def start() -> dict:
    _local.t = {"steps": {}, "llm": [], "label": ""}
    return _local.t


def current() -> dict | None:
    return getattr(_local, "t", None)


@contextmanager
def step(name: str, llm: bool = False):
    """Time a block in milliseconds (summed if the step repeats). llm=True labels model calls made inside it."""
    cur = current()
    t0 = time.perf_counter()
    previous = cur["label"] if cur else ""
    if cur is not None and llm:
        cur["label"] = name
    try:
        yield
    finally:
        if cur is not None:
            cur["steps"][name] = round(cur["steps"].get(name, 0.0) + (time.perf_counter() - t0) * 1000, 1)
            cur["label"] = previous


def llm_call(provider: str, model: str, seconds: float, tokens_in: int | None, tokens_out: int | None) -> None:
    """One model call: who served it, how long it took and how many tokens went in and out."""
    cur = current()
    if cur is None:
        return
    cur["llm"].append({"step": cur["label"] or "llm", "provider": provider or "", "model": model or "",
                       "s": round(seconds, 2), "in": tokens_in, "out": tokens_out,
                       "tok_s": round(tokens_out / seconds, 1) if tokens_out and seconds > 0 else None})


def summary(total_s: float) -> str:
    """One readable line for the server log."""
    cur = current() or {"steps": {}, "llm": []}
    parts = [f"total {total_s:.2f}s"]
    for name, ms in cur["steps"].items():
        calls = [c for c in cur["llm"] if c["step"] == name]
        extra = "".join(f" [{c['provider']} {c['in']}->{c['out']} tok, {c['tok_s']} tok/s]" for c in calls)
        parts.append(f"{name} {ms / 1000:.2f}s{extra}" if ms >= 1000 else f"{name} {ms:.0f}ms{extra}")
    return " | ".join(parts)
