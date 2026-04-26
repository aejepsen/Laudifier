# backend/api/main.py
"""
Laudifier — Backend FastAPI.
App factory + middleware + montagem dos routers. Lógica de negócio fica nos
módulos de routes/.
"""
import logging

# Silencia libs ruidosas — reduz volume de ingestão no Log Analytics.
for _noisy in ("httpx", "httpcore", "sentence_transformers", "langfuse", "qdrant_client", "urllib3"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .auth import UserContext, verify_token  # re-export p/ tests/test_concurrency
from .memory_routes import router as memory_router
from .middleware import register_middlewares
from .pipeline_routes import router as pipeline_router
from .routes.auth import router as auth_router
from .routes.dashboard import router as dashboard_router
from .routes.debug import router as debug_router
from .routes.health import router as health_router
from .routes.laudos import router as laudos_router
from .routes.repositorio import router as repositorio_router
from ._shared import limiter

_IS_PROD = os.getenv("APP_ENV") == "production"
_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Boot: cria collection Qdrant se ausente + pré-carrega Whisper na RAM.
    Reduz cold start do primeiro request (~2min → ~5s).
    """
    # ── Qdrant: garante collection com named vector "dense" ──────────────────
    try:
        from qdrant_client import AsyncQdrantClient
        from qdrant_client.models import Distance, VectorParams

        qdrant_url = os.getenv("QDRANT_URL", "http://qdrant:6333")
        qdrant_key = os.getenv("QDRANT_API_KEY") or None
        collection = os.getenv("QDRANT_COLLECTION", "laudos_medicos")
        emb_dim    = int(os.getenv("EMB_DIM", "1024"))  # multilingual-e5-large

        client = AsyncQdrantClient(url=qdrant_url, api_key=qdrant_key, timeout=30, check_compatibility=False)
        try:
            existing = {c.name for c in (await client.get_collections()).collections}
            if collection not in existing:
                _log.info(f"[startup] criando collection Qdrant '{collection}'…")
                await client.create_collection(
                    collection_name=collection,
                    vectors_config={"dense": VectorParams(size=emb_dim, distance=Distance.COSINE)},
                )
                for field in ["especialidade", "tipo_laudo", "source_name", "modalidade", "medico_id", "source"]:
                    await client.create_payload_index(collection, field, "keyword")
                _log.info(f"[startup] collection '{collection}' criada com índices")
            else:
                _log.info(f"[startup] collection '{collection}' já existe")
        finally:
            await client.close()
    except Exception as e:
        _log.warning(f"[startup] falha Qdrant init (segue sem RAG): {e}")

    # ── Whisper: pré-carrega modelo na RAM (cold start → warm) ───────────────
    try:
        import whisper as wh
        model_name = os.getenv("WHISPER_MODEL", "small")
        _log.info(f"[startup] pré-carregando Whisper '{model_name}'…")
        wh.load_model(model_name)  # cache em /home/app/.cache/whisper
        _log.info(f"[startup] Whisper '{model_name}' carregado")
    except Exception as e:
        _log.warning(f"[startup] falha pre-load Whisper (segue lazy): {e}")

    yield


app = FastAPI(
    title="Laudifier API",
    version="1.0.0",
    description="Gerador de laudos médicos com IA",
    docs_url=None if _IS_PROD else "/docs",
    redoc_url=None if _IS_PROD else "/redoc",
    openapi_url=None if _IS_PROD else "/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:4200").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

register_middlewares(app)

app.include_router(auth_router)
app.include_router(laudos_router)
app.include_router(repositorio_router)
app.include_router(dashboard_router)
app.include_router(health_router)
app.include_router(memory_router)
app.include_router(pipeline_router)

# Endpoints admin-only — deixar por último para não confundir grep de rotas públicas.
app.include_router(debug_router)

__all__ = ["app", "verify_token", "UserContext"]
