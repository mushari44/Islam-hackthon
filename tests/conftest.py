"""Shared test setup: a throwaway SQLite database, demo data, and no calls to Claude.

Tests are split by owner: tests/rag and tests/community (Mushari), tests/calls (Eman), tests/core (shared).
"""
import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="sabeeli-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["SABEELI_OFFLINE"] = "1"      # never spend API credits in tests
os.environ["SEED_DEMO"] = "1"
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DEMO_PASSWORD", "sabeeli-demo")

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def seeker(client):
    """Headers for a fresh anonymous seeker session."""
    token = client.post("/api/session").json()["token"]
    return {"X-Seeker": token, "_token": token}


def seeker_headers(s):
    return {"X-Seeker": s["X-Seeker"]}


@pytest.fixture()
def daai_login(client):
    def login(username="khalid"):
        res = client.post("/api/daai/login", json={"username": username, "password": os.environ["DEMO_PASSWORD"]}).json()
        return {"Authorization": f"Bearer {res['token']}", "_token": res["token"]}
    return login
