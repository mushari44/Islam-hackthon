#!/bin/sh
# Container start for GPU mode (compose.yaml, sabeeli-gpu): builds the E5 index on the first start, then runs the app.
# `docker build` can't use a GPU, so the index is built here, at run time, and kept in the sabeeli-vectors volume.
set -e
if [ "$SABEELI_BUILD_INDEX" = "1" ] && ! ls data/cache/vectors/*/index.faiss >/dev/null 2>&1; then
  # A real CUDA check: the card must also run a kernel (an unsupported card can report CUDA but fail here).
  if python -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() and (torch.ones(1, device='cuda') + 1).item() == 2 else 1)" 2>/dev/null; then
    echo "GPU found: $(python -c 'import torch; print(torch.cuda.get_device_name(0))')"
    echo "Building the E5 index on the GPU (first start only; downloads about 2.2 GB, then a few minutes)..."
    python scripts/build_embeddings.py || echo "WARNING: the E5 index build failed; starting with BM25 search only"
  elif [ "$SABEELI_INDEX_ON_CPU" = "1" ]; then
    echo "WARNING: no usable NVIDIA GPU; building the E5 index on the CPU as asked (SABEELI_INDEX_ON_CPU=1). This takes about 3 HOURS."
    python scripts/build_embeddings.py || echo "WARNING: the E5 index build failed; starting with BM25 search only"
  else
    echo "WARNING: no usable NVIDIA GPU in this container; starting with BM25 search only."
    echo "         See README, GPU mode. To build on the CPU anyway (about 3 hours), set SABEELI_INDEX_ON_CPU=1 in .env."
  fi
fi
echo "Starting Sabeeli on port ${PORT:-8000}"
exec uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
