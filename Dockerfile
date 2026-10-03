# One container for the whole app: the React build is served by FastAPI.
# Build:  docker build -t sabeeli .     Run:  docker run -p 8000:8000 --env-file .env sabeeli

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
COPY backend ./backend
COPY data/corpus ./data/corpus
COPY --from=web /app/frontend/dist ./frontend/dist
EXPOSE 8000
# Hosts such as Render set PORT; locally it falls back to 8000.
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
