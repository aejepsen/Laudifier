# backend/api/middleware.py
"""HTTP middlewares: query counter (N+1) e security headers."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from starlette.responses import Response

from ._query_counter import log_if_over_threshold, reset_query_counter
from ._shared import _IS_PROD

logger = logging.getLogger(__name__)


def register_middlewares(app: FastAPI) -> None:
    """Anexa todos os middlewares HTTP à aplicação."""

    @app.middleware("http")
    async def query_counter_middleware(request: Request, call_next):
        """Reseta counter por request, loga warning se threshold excedido."""
        reset_query_counter()
        response = await call_next(request)
        log_if_over_threshold(request.url.path)
        return response

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception:
            # Boundary de request: logger.exception preserva contexto e cadeia de causas.
            # Captura genérica é correta aqui — último bastião antes do cliente HTTP.
            logger.exception("[Middleware] Exceção não tratada na rota %s", request.url.path)
            response = Response("Internal Server Error", status_code=500)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "frame-ancestors 'none';"
        )
        if _IS_PROD:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
