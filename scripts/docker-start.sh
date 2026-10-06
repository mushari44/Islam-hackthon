#!/bin/sh
# Container start for GPU mode (compose.yaml, sabeeli-gpu): builds the E5 index on the first start, then runs the app.
# `docker build` can't use a GPU, so the index is built here, at run time, and kept in the sabeeli-vectors volume.
set -e
if [ "$SABEELI_BUILD_INDEX" = "1" ] && ! ls data/cache/vectors/*/index.faiss >/dev/null 2>&1; then
  if python -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; then
    echo "Building the E5 index on the GPU (first start only; downloads about 2.2 GB, then a few minutes)..."
    python scripts/build_embeddings.py || echo "WARNING: the E5 index build failed; starting with BM25 search only"
  else
    echo "WARNING: no NVIDIA GPU is visible to Docker; starting with BM25 search only (see README, GPU mode)"
  fi
fi
exec uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
