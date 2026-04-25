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

app = FastAPI(
    title="Laudifier API",
    version="1.0.0",
    description="Gerador de laudos médicos com IA",
    docs_url=None if _IS_PROD else "/docs",
    redoc_url=None if _IS_PROD else "/redoc",
    openapi_url=None if _IS_PROD else "/openapi.json",
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
