"""Shared test setup: a throwaway SQLite database, demo data, and no calls to Claude.

Tests are split by owner: tests/rag and tests/community (Mushari), tests/calls and tests/auth (Eman).
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
os.environ.setdefault("DEMO_PASSWORD", "123")

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


_callers = [0]


def sign_up(client, headers: dict) -> dict:
    """Signs this browser session up to a fresh account (asking for a call needs one) and returns its headers."""
    _callers[0] += 1
    res = client.post("/api/account/signup", headers=seeker_headers(headers),
                      json={"username": f"tcaller_{_callers[0]}", "password": "long-pass-1", "gender": "m", "age_band": "25_34"})
    assert res.status_code == 200
    return headers


def signed_in(client) -> dict:
    """Headers for a new browser session signed in to a fresh account."""
    return sign_up(client, {"X-Seeker": client.post("/api/session").json()["token"]})


@pytest.fixture()
def caller(client, seeker):
    """Like `seeker`, but signed in to a fresh account."""
    return sign_up(client, seeker)


def seeker_headers(s):
    return {"X-Seeker": s["X-Seeker"]}


@pytest.fixture()
def daai_login(client):
    def login(username="khalid"):
        res = client.post("/api/daai/login", json={"username": username, "password": os.environ["DEMO_PASSWORD"]}).json()
        return {"Authorization": f"Bearer {res['token']}", "_token": res["token"]}
    return login
