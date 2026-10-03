"""Tests use BM25 only, so results don't depend on a locally built vector index (see features/rag/embeddings.py)."""
import os

os.environ["SABEELI_EMBEDDINGS"] = "0"
