# ─── Stage 1: builder ────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
# Instala torch CPU-only PRIMEIRO — evita que sentence-transformers puxe torch+CUDA (~5.5 GB)
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        torch==2.5.1+cpu \
        --extra-index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# Pré-baixa o modelo de embedding no build — evita download em runtime e erro de permissão
RUN HF_HOME=/tmp/hf_model_cache python -c \
    "from sentence_transformers import SentenceTransformer; \
     SentenceTransformer('intfloat/multilingual-e5-large', cache_folder='/tmp/hf_model_cache'); \
     print('Modelo multilingual-e5-large baixado com sucesso')"

# ─── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.11-slim

# ffmpeg necessário para Whisper processar áudio
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r app && useradd -r -g app -d /home/app -m app

WORKDIR /app

# Deps do stage builder (site-packages + executáveis como uvicorn)
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Código — sem .env, sem tests, sem __pycache__ (garantido pelo .dockerignore)
COPY --chown=app:app . .

# Symlink /workspace/backend → /app para que imports relativos (from ..agents) funcionem
# Deve rodar como root, antes de USER app
RUN mkdir -p /workspace && ln -sf /app /workspace/backend

# Copia modelo pré-baixado do builder e garante permissões corretas para o user app
COPY --from=builder /tmp/hf_model_cache /home/app/.cache/huggingface
RUN chown -R app:app /home/app/.cache

USER app

ENV WHISPER_CACHE_DIR=/home/app/.cache/whisper
ENV HF_HOME=/home/app/.cache/huggingface
ENV TRANSFORMERS_CACHE=/home/app/.cache/huggingface
ENV PYTHONPATH=/workspace

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

EXPOSE 8000
CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
