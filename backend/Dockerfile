# Ticket Assistant backend: FastAPI + hybrid search (BM25 + bge-small embeddings).
# Build from backend/:  docker build -t ticket-assistant-backend .
# Run:                  docker run -p 8000:8000 --env-file .env ticket-assistant-backend
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1 \
    EMBEDDER=fastembed

WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY data ./data
COPY scripts ./scripts

# Download the embedding model, cache the document vectors and train the classifier inside the image,
# so the container starts in seconds instead of doing this on the first request.
# Model -> /app/.cache/fastembed, vectors + classifier.joblib -> /app/data/index (read at runtime).
RUN python scripts/build_index.py

# Run as a non-root user. It owns /app so the vector cache can be rebuilt if the corpus changes.
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

EXPOSE 8000
# Render (and most hosts) set $PORT; 8000 when run locally.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
