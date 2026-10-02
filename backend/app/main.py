"""Sabeeli web app: wires the shared core, the four features and the static frontend.

Run:  uvicorn backend.app.main:app --port 8000      (from the repository root)
"""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .core.config import settings
from .core.db import SessionLocal, init_db
from .features.auth import routes as auth_routes
from .features.auth.seed import seed_accounts
from .features.calls import referral as calls_referral
from .features.calls import routes as calls_routes
from .features.calls import signalling as calls_signalling
from .features.community import routes as community_routes
from .features.community import seed as community_seed
from .features.rag import routes as rag_routes
from .features.rag.corpus import get_corpus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sabeeli")


def _warm_up() -> None:
    """Load the corpus and verse matcher off the request path (a few seconds on first start)."""
    from .features.rag.quran_match import get_matcher
    stats = get_corpus().stats()
    get_matcher()
    log.info("corpus ready: %s", stats)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if settings.seed_demo:
        db = SessionLocal()
        try:
            community_seed.seed(db, seed_accounts(db))
        finally:
            db.close()
    threading.Thread(target=_warm_up, daemon=True).start()
    log.info("Sabeeli started (AI %s, model %s)", "on" if settings.llm_enabled else "off: sources-only mode",
             settings.model)
    yield


app = FastAPI(title="Sabeeli", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)

app.include_router(auth_routes.router)
app.include_router(rag_routes.router)
app.include_router(community_routes.router)
app.include_router(calls_routes.router)
app.include_router(calls_referral.router)
app.include_router(calls_signalling.ws_router)


@app.get("/api/health")
def health():
    return {"ok": True, "ai": settings.llm_enabled, "model": settings.model if settings.llm_enabled else None,
            "corpus": get_corpus().stats()}


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):  # noqa: ARG001
    log.exception("unhandled error")
    return JSONResponse({"detail": "server error"}, status_code=500)


# --- frontend (React, built into frontend/dist) --------------------------------
DIST = settings.frontend_dir
NOT_BUILT = """<!doctype html><meta charset="utf-8"><title>Sabeeli</title>
<body style="font-family:system-ui;padding:40px;line-height:1.7">
<h1>Sabeeli API is running</h1>
<p>The React frontend is not built yet. Run <code>npm install</code> and <code>npm run build</code> in <code>frontend/</code>,
or use <code>npm run dev</code> there and open http://localhost:5173.</p>
<p>API docs: <a href="/api/docs">/api/docs</a></p></body>"""

if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/", include_in_schema=False)
def index():
    page = DIST / "index.html"
    if not page.exists():
        return HTMLResponse(NOT_BUILT)
    return FileResponse(page, headers={"Cache-Control": "no-cache"})


@app.get("/{name}", include_in_schema=False)
def root_file(name: str):
    """Top-level files from the build (icon.svg, manifest.webmanifest)."""
    path = (DIST / name).resolve()
    if DIST.resolve() not in path.parents or not path.is_file():
        raise HTTPException(404)
    media = "application/manifest+json" if name.endswith(".webmanifest") else None
    return FileResponse(path, media_type=media)
