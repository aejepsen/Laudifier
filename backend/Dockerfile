# ─── Stage 1: builder ────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/deps -r requirements.txt

# ─── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.11-slim

# ffmpeg necessário para Whisper processar áudio
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r app && useradd -r -g app -d /home/app -m app

WORKDIR /app

# Deps do stage builder
COPY --from=builder /deps /usr/local/lib/python3.11/site-packages

# Código — sem .env, sem tests, sem __pycache__ (garantido pelo .dockerignore)
COPY --chown=app:app . .

USER app

# Whisper carrega do volume montado em runtime — nunca bake no build
ENV WHISPER_CACHE_DIR=/home/app/.cache/whisper

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
