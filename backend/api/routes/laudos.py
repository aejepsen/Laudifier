# backend/api/routes/laudos.py
"""Endpoints de geração, edição, listagem, feedback e exportação de laudos."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from ...agents.laudo_agent import (
    corrigir_laudo_stream,
    gerar_conclusao_stream,
    gerar_laudo_stream,
)
from ...services.export_service import ExportService
from ...services.laudo_service import LaudoService
from ..auth import UserContext, verify_token
from .._helpers import _memorizar_correcao, _re_indexar_laudo_aprovado
from .._shared import _SSE_STREAM_ERRORS, langfuse, limiter
from ..models import (
    ConclusaoRequest,
    CorrecaoRequest,
    FeedbackRequest,
    LaudoRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


# ─── Geração de Laudo ────────────────────────────────────────────────────────

@router.post("/laudos/gerar")
@limiter.limit("30/minute")
async def gerar_laudo(
    request: Request,
    body: LaudoRequest,
    user: UserContext = Depends(verify_token),
):
    """
    Gera laudo médico via streaming SSE.
    Usa repositório Qdrant como contexto principal.
    Fallback para conhecimento base do Claude quando repositório não tem referências.
    """
    laudo_id = body.laudo_id or str(uuid.uuid4())

    trace = langfuse.trace(
        name="gerar-laudo",
        user_id=user.id,
        input={"especialidade": body.especialidade, "solicitacao": body.solicitacao[:200]},
        metadata={"laudo_id": laudo_id},
    )

    async def event_gen():
        laudo_completo = ""
        try:
            async for chunk in gerar_laudo_stream(
                solicitacao=body.solicitacao,
                especialidade=body.especialidade,
                dados_clinicos=body.dados_clinicos,
                user_id=user.id,
            ):
                if chunk.get("type") == "token":
                    laudo_completo += chunk.get("text", "")
                if chunk.get("type") == "done":
                    laudo_final = chunk.get("laudo") or laudo_completo
                    task = asyncio.create_task(
                        LaudoService(user.id).salvar(
                            laudo_id=laudo_id,
                            especialidade=body.especialidade,
                            solicitacao=body.solicitacao,
                            laudo=laudo_final,
                            tipo_geracao=chunk.get("tipo_geracao", ""),
                            laudos_ref=chunk.get("laudos_ref", []),
                        )
                    )
                    task.add_done_callback(
                        lambda t: logger.error("[Salvar laudo] Falhou", exc_info=t.exception()) if t.exception() else None
                    )
                    trace.update(output={"laudo_id": laudo_id, "tipo_geracao": chunk.get("tipo_geracao")})
                    done_payload = {
                        "type":            "done",
                        "laudo_id":        laudo_id,
                        "laudo":           laudo_final,
                        "tipo_geracao":    chunk.get("tipo_geracao", ""),
                        "campos_faltando": chunk.get("campos_faltando", []),
                        "laudos_ref":      chunk.get("laudos_ref", []),
                    }
                    yield f"data: {json.dumps(done_payload)}\n\n"
                    return
                yield f"data: {json.dumps(chunk)}\n\n"
        except _SSE_STREAM_ERRORS:
            logger.error("[Gerar laudo] Erro no streaming", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': 'Erro ao gerar laudo'})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/laudos/transcrever")
@limiter.limit("10/minute")
async def transcrever_audio(
    request: Request,
    audio: UploadFile = File(...),
    user:  UserContext = Depends(verify_token),
):
    """
    Transcrição server-side com Whisper (fallback quando browser não suporta Web Speech API).
    Browser-first: o Angular usa Web Speech API diretamente quando disponível.
    """
    MAX_AUDIO_BYTES = 25 * 1024 * 1024
    contents = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(contents) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="Arquivo de áudio muito grande (máx 25 MB)")

    try:
        import whisper as wh
    except ImportError:
        raise HTTPException(status_code=501, detail="Transcrição server-side não disponível. Use o microfone do browser.")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name
        model  = wh.load_model(os.getenv("WHISPER_MODEL", "small"))
        result = model.transcribe(tmp_path, language="pt", fp16=False)
        return {"transcript": result["text"].strip()}
    except Exception:
        logger.error("[Transcrição] Erro ao processar áudio", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao transcrever áudio")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ─── Laudos Salvos ───────────────────────────────────────────────────────────

@router.get("/laudos")
async def listar_laudos(
    page:          int           = Query(default=0, ge=0),
    size:          int           = Query(default=20, ge=1, le=100),
    especialidade: Optional[str] = None,
    user:          UserContext   = Depends(verify_token),
):
    return await LaudoService(user.id).listar(page, size, especialidade)


@router.get("/laudos/{laudo_id}")
async def get_laudo(laudo_id: str, user: UserContext = Depends(verify_token)):
    laudo = await LaudoService(user.id).get(laudo_id)
    if not laudo:
        raise HTTPException(status_code=404, detail="Laudo não encontrado")
    return laudo


@router.put("/laudos/{laudo_id}")
async def atualizar_laudo(
    laudo_id:      str,
    laudo_editado: str = Query(..., max_length=50000),
    user:          UserContext = Depends(verify_token),
):
    """Salva edições do médico no laudo gerado."""
    await LaudoService(user.id).atualizar(laudo_id, laudo_editado)
    return {"status": "ok"}


@router.delete("/laudos/{laudo_id}")
async def deletar_laudo(laudo_id: str, user: UserContext = Depends(verify_token)):
    """Remove laudo do usuário (direito de exclusão — LGPD art. 18, VI)."""
    laudo = await LaudoService(user.id).get(laudo_id)
    if not laudo:
        raise HTTPException(status_code=404, detail="Laudo não encontrado")
    await LaudoService(user.id).deletar(laudo_id)
    return {"status": "deleted"}


@router.post("/laudos/{laudo_id}/corrigir")
@limiter.limit("30/minute")
async def corrigir_laudo(
    request:  Request,
    laudo_id: str,
    body:     CorrecaoRequest,
    user:     UserContext = Depends(verify_token),
):
    """
    Etapa 3 — Correção assistida.
    Médico fornece achados em linguagem livre; Laudifier reescreve em
    terminologia radiológica correta usando RAG de frases especializadas.
    """
    if body.laudo_atual:
        laudo_conteudo  = body.laudo_atual
        especialidade   = ""
    else:
        laudo = await LaudoService(user.id).get(laudo_id)
        if not laudo:
            raise HTTPException(status_code=404, detail="Laudo não encontrado")
        laudo_conteudo  = laudo.get("laudo_editado") or laudo["laudo"]
        especialidade   = laudo.get("especialidade", "")

    async def event_gen():
        laudo_corrigido = ""
        try:
            async for chunk in corrigir_laudo_stream(
                laudo_atual=laudo_conteudo,
                achados=body.achados,
                especialidade=especialidade,
                user_id=user.id,
            ):
                if chunk.get("type") == "token":
                    laudo_corrigido += chunk.get("text", "")
                if chunk.get("type") == "done":
                    await LaudoService(user.id).atualizar(laudo_id, laudo_corrigido)
                    yield f"data: {json.dumps({**chunk, 'laudo_id': laudo_id})}\n\n"
                    return
                yield f"data: {json.dumps(chunk)}\n\n"
        except _SSE_STREAM_ERRORS:
            logger.error("[Corrigir laudo] Erro no streaming", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': 'Erro ao corrigir laudo'})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/laudos/{laudo_id}/concluir")
@limiter.limit("30/minute")
async def gerar_conclusao(
    request:  Request,
    laudo_id: str,
    body:     ConclusaoRequest,
    user:     UserContext = Depends(verify_token),
):
    """
    Etapa 4 — Geração de conclusão.
    Com o laudo de achados preenchido, Claude gera a IMPRESSÃO DIAGNÓSTICA
    e preenche os dados do paciente para o laudo final.
    """
    laudo = await LaudoService(user.id).get(laudo_id)
    if not laudo:
        raise HTTPException(status_code=404, detail="Laudo não encontrado")

    async def event_gen():
        laudo_final = ""
        try:
            async for chunk in gerar_conclusao_stream(
                laudo_atual=laudo.get("laudo_editado") or laudo["laudo"],
                dados_paciente=body.dados_paciente,
                especialidade=laudo.get("especialidade", ""),
            ):
                if chunk.get("type") == "token":
                    laudo_final += chunk.get("text", "")
                if chunk.get("type") == "done":
                    await LaudoService(user.id).atualizar(laudo_id, laudo_final)
                    yield f"data: {json.dumps({**chunk, 'laudo_id': laudo_id})}\n\n"
                    return
                yield f"data: {json.dumps(chunk)}\n\n"
        except _SSE_STREAM_ERRORS:
            logger.error("[Conclusão] Erro no streaming", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': 'Erro ao gerar conclusão'})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/laudos/{laudo_id}/feedback")
async def feedback(
    laudo_id: str,
    body:     FeedbackRequest,
    user:     UserContext = Depends(verify_token),
):
    """
    Feedback do médico: aprovou ou corrigiu o laudo.
    Laudos aprovados podem ser re-indexados no Qdrant para melhorar futuras gerações.
    """
    await LaudoService(user.id).registrar_feedback(laudo_id, body.aprovado, body.correcoes)

    if body.aprovado:
        task = asyncio.create_task(_re_indexar_laudo_aprovado(laudo_id, user.id))
        task.add_done_callback(
            lambda t: logger.error("[Re-indexação] Task falhou", exc_info=t.exception()) if t.exception() else None
        )
    if body.correcoes:
        task = asyncio.create_task(_memorizar_correcao(laudo_id, user.id, body.correcoes))
        task.add_done_callback(
            lambda t: logger.error("[Mem0 correção] Task falhou", exc_info=t.exception()) if t.exception() else None
        )
    return {"status": "ok"}


# ─── Exportação ──────────────────────────────────────────────────────────────

_FORMATOS_VALIDOS = frozenset({"pdf", "docx", "txt"})

@router.get("/laudos/{laudo_id}/exportar/{formato}")
async def exportar_laudo(
    laudo_id: str,
    formato:  str,
    user:     UserContext = Depends(verify_token),
):
    """Exporta o laudo em PDF, DOCX ou TXT para impressão/assinatura."""
    if formato not in _FORMATOS_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Formato inválido. Use: {', '.join(_FORMATOS_VALIDOS)}")

    laudo = await LaudoService(user.id).get(laudo_id)
    if not laudo:
        raise HTTPException(status_code=404, detail="Laudo não encontrado")

    svc  = ExportService()
    path = await svc.exportar(laudo, formato)

    media = {
        "pdf":  "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "txt":  "text/plain",
    }
    return FileResponse(path, media_type=media[formato],
                        filename=f"laudo_{laudo_id[:8]}.{formato}")
