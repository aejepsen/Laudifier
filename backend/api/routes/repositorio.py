# backend/api/routes/repositorio.py
"""Endpoint de upload de laudos de referência (admin only)."""
from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..auth import UserContext, verify_token
from .._helpers import _ingerir_laudo_repositorio
from .._shared import storage

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/repositorio/upload")
async def upload_laudo_referencia(
    arquivo:       UploadFile = File(...),
    especialidade: str = Form("geral"),
    tipo_laudo:    str = Form(""),
    user:          UserContext = Depends(verify_token),
):
    """
    Adiciona laudos ao repositório de referência via pipeline de ingestão.
    Apenas médicos com role 'admin' podem adicionar ao repositório.
    """
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Apenas administradores podem adicionar ao repositório")

    MAX_DOC_BYTES = 10 * 1024 * 1024
    contents = await arquivo.read(MAX_DOC_BYTES + 1)
    if len(contents) > MAX_DOC_BYTES:
        raise HTTPException(status_code=400, detail="Arquivo muito grande (máx 10 MB)")

    job_id = str(uuid.uuid4())
    url    = storage.upload_document(contents, arquivo.filename or "upload", user.id)

    task = asyncio.create_task(_ingerir_laudo_repositorio(
        job_id=job_id, url=url, filename=arquivo.filename or "upload",
        especialidade=especialidade, tipo_laudo=tipo_laudo, user_id=user.id,
    ))
    task.add_done_callback(
        lambda t: logger.error("[Ingestão] Task falhou", extra={"job_id": job_id}, exc_info=t.exception()) if t.exception() else None
    )
    return {"job_id": job_id, "status": "queued"}
