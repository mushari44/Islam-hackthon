# One container for the whole app: the React build is served by FastAPI.
# Easiest: docker compose up --build (compose.yaml). Or: docker build -t sabeeli . && docker run -p 8000:8000 sabeeli
# (add --env-file .env to use the settings in .env)
# Full mode (FULL=1, `docker compose --profile full up --build sabeeli-full`) also builds «بينات» from the
# package's link, which takes a few minutes. GPU mode (GPU=1, `docker compose --profile gpu up --build sabeeli-gpu`)
# adds the hybrid search (BM25 + the E5 embedding model) for an NVIDIA GPU. `docker build` can't use a GPU, so the
# E5 index is built when the container first starts (scripts/docker-start.sh) and kept in a volume.

FROM node:20-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
ARG FULL=0
ARG GPU=0
ENV HF_HOME=/app/.hf
COPY requirements-embeddings.txt ./
RUN if [ "$FULL" = "1" ]; then pip install --no-cache-dir pymupdf; fi
# The CUDA build of PyTorch (about 2.5 GB), then the E5 / LangChain / FAISS packages.
RUN if [ "$GPU" = "1" ]; then \
      pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cu124 && \
      pip install --no-cache-dir -r requirements-embeddings.txt; \
    fi
COPY backend ./backend
COPY data/corpus ./data/corpus
COPY scripts ./scripts
# «بينات» is built here from the package's own link (its rights are reserved, so it is never in the repo);
# if the site can't be reached the app still runs without it.
RUN if [ "$FULL" = "1" ]; then \
      (python scripts/ingest_bayyinat.py || echo "WARNING: could not build Bayyinat; continuing without it") && \
      rm -rf data/raw; \
    fi
COPY --from=web /app/frontend/dist ./frontend/dist
EXPOSE 8000
# Hosts such as Render set PORT; locally it falls back to 8000.
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
