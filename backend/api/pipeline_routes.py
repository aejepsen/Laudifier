# backend/api/pipeline_routes.py
"""
Rotas de administração do pipeline de indexação.
Protegidas por ADMIN_API_KEY — nunca expostas a usuários finais.
"""

import logging
import os
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

ADMIN_KEY   = os.getenv("ADMIN_API_KEY", "")
QDRANT_URL  = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_KEY  = os.getenv("QDRANT_API_KEY", "")
COLLECTION  = os.getenv("QDRANT_COLLECTION", "laudos_medicos")
EMB_MODEL   = "intfloat/multilingual-e5-large"
EMB_DIM     = 1024
CHUNK_SIZE    = 1500
CHUNK_OVERLAP = 150

router = APIRouter(prefix="/admin/pipeline", tags=["pipeline"])

# ── Lazy singletons ───────────────────────────────────────────────────────────

_model  = None
_client = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info(f"[Pipeline] Carregando modelo {EMB_MODEL}...")
        _model = SentenceTransformer(EMB_MODEL)
        logger.info("[Pipeline] Modelo carregado.")
    return _model


def _get_client():
    global _client
    if _client is None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
        _client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_KEY or None)
        # Cria coleção se não existir
        existing = [c.name for c in _client.get_collections().collections]
        if COLLECTION not in existing:
            logger.info(f"[Pipeline] Criando coleção '{COLLECTION}'...")
            _client.create_collection(
                collection_name=COLLECTION,
                vectors_config=VectorParams(size=EMB_DIM, distance=Distance.COSINE),
            )
            for field in ["especialidade", "tipo_laudo", "source_name", "source"]:
                _client.create_payload_index(COLLECTION, field, "keyword")
    return _client


# ── Auth ──────────────────────────────────────────────────────────────────────

def _check_admin(x_admin_key: str = Header(...)):
    if not ADMIN_KEY or x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Chave admin inválida")


# ── Chunking ─────────────────────────────────────────────────────────────────

def _chunk(texto: str) -> list[str]:
    texto = texto.strip()
    if not texto:
        return []
    sec = re.compile(r'^([A-ZÁÉÍÓÚÂÊÔÃÕÇ\s/:]{3,}[:])\s*$', re.MULTILINE)
    parts = sec.split(texto)
    chunks = []
    if len(parts) > 1:
        i = 1
        while i < len(parts) - 1:
            bloco = f"{parts[i]}\n{parts[i+1].strip()}"
            if bloco.strip():
                chunks.append(bloco)
            i += 2
    else:
        start = 0
        while start < len(texto):
            end = min(start + CHUNK_SIZE, len(texto))
            chunks.append(texto[start:end])
            if end == len(texto):
                break
            start = end - CHUNK_OVERLAP
    return [c for c in chunks if len(c.strip()) > 50]


def _limpar(texto: str) -> str:
    lines = texto.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("==="):
            return "\n".join(lines[i + 1:]).strip()
    return texto


# ── Endpoints ─────────────────────────────────────────────────────────────────

class StatusResponse(BaseModel):
    collection: str
    points:     int
    model:      str


@router.get("/status")
async def status(x_admin_key: str = Header(...)):
    _check_admin(x_admin_key)
    client = _get_client()
    info   = client.get_collection(COLLECTION)
    return StatusResponse(
        collection=COLLECTION,
        points=info.points_count or 0,
        model=EMB_MODEL,
    )


@router.post("/indexar")
async def indexar(
    files:         list[UploadFile] = File(...),
    especialidade: str              = Form("geral"),
    tipo_laudo:    str              = Form(""),
    source:        str              = Form("upload"),
    x_admin_key:   str              = Header(...),
):
    """
    Recebe até 50 arquivos .txt por chamada, embute server-side e indexa no Qdrant.
    """
    _check_admin(x_admin_key)
    model  = _get_model()
    client = _get_client()

    from qdrant_client.models import PointStruct
    import asyncio

    total_chunks = 0
    total_files  = 0
    erros        = []

    for upload in files:
        try:
            raw   = (await upload.read()).decode("utf-8", errors="ignore")
            texto = _limpar(raw)
            chunks = _chunk(texto)
            if not chunks:
                continue

            prefixed = [f"passage: {c}" for c in chunks]
            vecs = await asyncio.to_thread(
                model.encode, prefixed,
                normalize_embeddings=True,
                show_progress_bar=False,
            )

            tipo = tipo_laudo or Path(upload.filename or "").stem[:80]
            points = [
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vecs[i].tolist(),
                    payload={
                        "content":       chunks[i],
                        "source_name":   upload.filename or "",
                        "source":        source,
                        "especialidade": especialidade,
                        "tipo_laudo":    tipo,
                        "aprovado":      True,
                    },
                )
                for i in range(len(chunks))
            ]
            client.upsert(collection_name=COLLECTION, points=points)
            total_chunks += len(points)
            total_files  += 1

        except Exception as e:
            logger.error(f"[Pipeline] Erro em {upload.filename}: {e}")
            erros.append({"file": upload.filename, "error": str(e)})

    info = client.get_collection(COLLECTION)
    return {
        "files_indexed":  total_files,
        "chunks_indexed": total_chunks,
        "total_in_qdrant": info.points_count,
        "errors":         erros,
    }


@router.delete("/limpar")
async def limpar_colecao(x_admin_key: str = Header(...)):
    """Remove todos os pontos da coleção (não a coleção em si)."""
    _check_admin(x_admin_key)
    client = _get_client()
    from qdrant_client.models import Filter
    client.delete(
        collection_name=COLLECTION,
        points_selector=Filter(must=[]),
    )
    return {"status": "ok", "collection": COLLECTION}
