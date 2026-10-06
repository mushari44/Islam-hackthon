"""Tests use BM25 only, so results don't depend on a locally built vector index (see features/rag/embeddings.py)."""
import os

os.environ["SABEELI_EMBEDDINGS"] = "0"


import pytest

from tests.conftest import sign_up


@pytest.fixture()
def seeker(client):
    """Community actions (join, post, book a spot) need an account, so the community tests' seeker has one."""
    token = client.post("/api/session").json()["token"]
    return sign_up(client, {"X-Seeker": token, "_token": token})


@pytest.fixture()
def caller(seeker):
    """The community seeker is already signed in."""
    return seeker
