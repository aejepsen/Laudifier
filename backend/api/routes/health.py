# backend/api/routes/health.py
"""Liveness e readiness probes."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import (
    ResponseHandlingException,
    UnexpectedResponse,
)

router = APIRouter()

_qdrant_health_client: QdrantClient | None = None


def _get_qdrant_health_client() -> QdrantClient:
    global _qdrant_health_client
    if _qdrant_health_client is None:
        _qdrant_health_client = QdrantClient(
            url=os.getenv("QDRANT_URL"),
            api_key=os.getenv("QDRANT_API_KEY") or None,
        )
    return _qdrant_health_client


@router.get("/health/live")
async def health_live():
    """Liveness probe — retorna imediatamente sem I/O externo."""
    return {"status": "ok"}


@router.get("/health")
@router.get("/health/ready")
async def health():
    """Readiness probe — verifica dependências reais."""
    services: dict[str, str] = {}

    try:
        _get_qdrant_health_client().get_collections()
        services["qdrant"] = "ok"
    except (UnexpectedResponse, ResponseHandlingException,
            ConnectionError, OSError, RuntimeError):
        services["qdrant"] = "error"

    status = "healthy" if all(v == "ok" for v in services.values()) else "degraded"
    return {
        "status":    status,
        "version":   "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services":  services,
    }
