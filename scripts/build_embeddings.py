"""Build the semantic-search index: every corpus passage embedded with multilingual E5-large.

Needs the optional packages:  pip install -r requirements-embeddings.txt
The model (intfloat/multilingual-e5-large, about 2.2 GB) downloads from Hugging Face on
first use. A GPU takes a few minutes; a CPU much longer. The index is written to
data/cache/vectors/<model>/ (git-ignored), and the app uses it on its next start.

Re-run it whenever data/corpus/ changes (for example after scripts/ingest_bayyinat.py).

Usage:  python scripts/build_embeddings.py [--batch-size 64]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["SABEELI_EMBEDDINGS"] = "0"  # don't load the old index while building a new one

from backend.app.features.rag import embeddings  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-size", type=int, default=64)
    args = ap.parse_args()
    print(f"embedding the corpus with {embeddings.model_name()} ...")
    stamp = embeddings.build_index(batch_size=args.batch_size)
    print(json.dumps(stamp, ensure_ascii=False, indent=1))
    print(f"saved to {embeddings.index_dir().relative_to(ROOT)}")
