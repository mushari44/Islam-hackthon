# One container for the whole app: the React build is served by FastAPI.
# Easiest: docker compose up --build (compose.yaml). Or: docker build -t sabeeli . && docker run -p 8000:8000 sabeeli
# (add --env-file .env to use the settings in .env)
# Full mode (FULL=1, `docker compose --profile full up --build sabeeli-full`) also builds «بينات» from the
# package's link, which takes a few minutes. E5=1 (`--profile e5 ... sabeeli-e5`) adds the E5 semantic-search
# index too, like the team's own copy: about 3 GB of downloads, and embedding the corpus on a CPU takes hours.

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
ARG E5=0
ENV HF_HOME=/app/.hf
COPY requirements-embeddings.txt ./
RUN if [ "$FULL" = "1" ]; then pip install --no-cache-dir pymupdf; fi
RUN if [ "$E5" = "1" ]; then \
      pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
      pip install --no-cache-dir -r requirements-embeddings.txt; \
    fi
COPY backend ./backend
COPY data/corpus ./data/corpus
COPY scripts ./scripts
# «بينات» is built here from the package's own link (its rights are reserved, so it is never in the repo);
# if the site can't be reached the app still runs without it. The E5 index is built after it, over the whole corpus.
RUN if [ "$FULL" = "1" ]; then \
      (python scripts/ingest_bayyinat.py || echo "WARNING: could not build Bayyinat; continuing without it") && \
      rm -rf data/raw; \
    fi
RUN if [ "$E5" = "1" ]; then python scripts/build_embeddings.py; fi
COPY --from=web /app/frontend/dist ./frontend/dist
EXPOSE 8000
# Hosts such as Render set PORT; locally it falls back to 8000.
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
