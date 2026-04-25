# backend/api/_shared.py
"""Singletons compartilhados entre os módulos de rotas (limiter, langfuse, storage)."""
import os

import anthropic
import httpx
from langfuse import Langfuse
from qdrant_client.http.exceptions import UnexpectedResponse, ResponseHandlingException
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..services.storage_service import StorageService

_IS_PROD = os.getenv("APP_ENV") == "production"

limiter = Limiter(key_func=get_remote_address)

langfuse = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
    host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
)

storage = StorageService()

# Erros esperados em geração SSE: rede do Claude, Qdrant, runtime do agent.
# CancelledError (BaseException em 3.8+) propaga e fecha o stream limpo.
_SSE_STREAM_ERRORS = (
    anthropic.APIError,
    httpx.HTTPError,
    UnexpectedResponse,
    ResponseHandlingException,
    RuntimeError,
    ValueError,
)
