# backend/api/main.py
"""
Laudifier — Backend FastAPI
Geração de laudos médicos com RAG + Claude knowledge fallback.
"""

import logging
import os
import json
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field
from langfuse import Langfuse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from qdrant_client import QdrantClient

from .auth import verify_token, UserContext
from ..agents.laudo_agent import gerar_laudo_stream
from ..services.storage_service import StorageService
from ..services.laudo_service import LaudoService
from ..services.export_service import ExportService
from ..services.memory_service import LaudifierMemory
from .memory_routes import router as memory_router
from .pipeline_routes import router as pipeline_router

logger  = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

langfuse = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
    host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
)

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
    allow_headers=["Authorization", "Content-Type"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

storage = StorageService()

app.include_router(memory_router)
app.include_router(pipeline_router)


# ─── Security headers ─────────────────────────────────────────────────────────

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
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


# ─── Models ────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email:    str
    password: str

class LaudoRequest(BaseModel):
    solicitacao:    str  = Field(..., max_length=5000)
    especialidade:  str  = Field(..., max_length=100)
    dados_clinicos: dict = Field(default={})
    laudo_id:       Optional[str] = None

class FeedbackRequest(BaseModel):
    aprovado:  bool
    correcoes: Optional[str] = Field(default=None, max_length=2000)

class TranscricaoRequest(BaseModel):
    audio_base64: str


# ─── Auth ──────────────────────────────────────────────────────────────────────

@app.post("/auth/token")
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest):
    """Login via email/senha. Credenciais no body, nunca na URL."""
    from supabase import create_client
    sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_ANON_KEY"))
    r  = sb.auth.sign_in_with_password({"email": body.email, "password": body.password})
    return {"access_token": r.session.access_token, "user_id": r.user.id}


# ─── Geração de Laudo ─────────────────────────────────────────────────────────

@app.post("/laudos/gerar")
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
                    task = asyncio.create_task(
                        LaudoService(user.id).salvar(
                            laudo_id=laudo_id,
                            especialidade=body.especialidade,
                            solicitacao=body.solicitacao,
                            laudo=laudo_completo,
                            tipo_geracao=chunk.get("tipo_geracao", ""),
                            laudos_ref=chunk.get("laudos_ref", []),
                        )
                    )
                    task.add_done_callback(
                        lambda t: logger.error("[Salvar laudo] Falhou", exc_info=t.exception()) if t.exception() else None
                    )
                    trace.update(output={"laudo_id": laudo_id, "tipo_geracao": chunk.get("tipo_geracao")})
                yield f"data: {json.dumps(chunk)}\n\n"
        except Exception as e:
            logger.error("[Gerar laudo] Erro no streaming", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': 'Erro ao gerar laudo'})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/laudos/transcrever")
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
    import tempfile
    import whisper as wh

    MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB
    contents = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(contents) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="Arquivo de áudio muito grande (máx 25 MB)")

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


# ─── Laudos Salvos ────────────────────────────────────────────────────────────

@app.get("/laudos")
async def listar_laudos(
    page:          int           = Query(default=0, ge=0),
    size:          int           = Query(default=20, ge=1, le=100),
    especialidade: Optional[str] = None,
    user:          UserContext   = Depends(verify_token),
):
    return await LaudoService(user.id).listar(page, size, especialidade)


@app.get("/laudos/{laudo_id}")
async def get_laudo(laudo_id: str, user: UserContext = Depends(verify_token)):
    laudo = await LaudoService(user.id).get(laudo_id)
    if not laudo:
        raise HTTPException(status_code=404, detail="Laudo não encontrado")
    return laudo


@app.put("/laudos/{laudo_id}")
async def atualizar_laudo(
    laudo_id:      str,
    laudo_editado: str = Query(..., max_length=50000),
    user:          UserContext = Depends(verify_token),
):
    """Salva edições do médico no laudo gerado."""
    await LaudoService(user.id).atualizar(laudo_id, laudo_editado)
    return {"status": "ok"}


@app.delete("/laudos/{laudo_id}")
async def deletar_laudo(laudo_id: str, user: UserContext = Depends(verify_token)):
    """Remove laudo do usuário (direito de exclusão — LGPD art. 18, VI)."""
    laudo = await LaudoService(user.id).get(laudo_id)
    if not laudo:
        raise HTTPException(status_code=404, detail="Laudo não encontrado")
    await LaudoService(user.id).deletar(laudo_id)
    return {"status": "deleted"}


@app.post("/laudos/{laudo_id}/feedback")
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


# ─── Exportação ───────────────────────────────────────────────────────────────

_FORMATOS_VALIDOS = frozenset({"pdf", "docx", "txt"})

@app.get("/laudos/{laudo_id}/exportar/{formato}")
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


# ─── Repositório ──────────────────────────────────────────────────────────────

@app.post("/repositorio/upload")
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

    MAX_DOC_BYTES = 10 * 1024 * 1024  # 10 MB
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


# ─── Dashboard ────────────────────────────────────────────────────────────────

@app.get("/dashboard/stats")
async def dashboard_stats(user: UserContext = Depends(verify_token)):
    svc = LaudoService(user.id)
    return await svc.get_stats()


# ─── Health ────────────────────────────────────────────────────────────────────

_qdrant_health_client: QdrantClient | None = None

def _get_qdrant_health_client() -> QdrantClient:
    global _qdrant_health_client
    if _qdrant_health_client is None:
        _qdrant_health_client = QdrantClient(
            url=os.getenv("QDRANT_URL"),
            api_key=os.getenv("QDRANT_API_KEY") or None,
        )
    return _qdrant_health_client


@app.get("/health/live")
async def health_live():
    """Liveness probe — retorna imediatamente sem I/O externo."""
    return {"status": "ok"}


@app.get("/health")
@app.get("/health/ready")
async def health():
    """Readiness probe — verifica dependências reais."""
    services: dict[str, str] = {}

    try:
        _get_qdrant_health_client().get_collections()
        services["qdrant"] = "ok"
    except Exception:
        services["qdrant"] = "error"

    status = "healthy" if all(v == "ok" for v in services.values()) else "degraded"
    return {
        "status":    status,
        "version":   "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services":  services,
    }


# ─── Background tasks ─────────────────────────────────────────────────────────

async def _re_indexar_laudo_aprovado(laudo_id: str, user_id: str) -> None:
    """Re-indexa laudo aprovado no Qdrant para enriquecer o repositório."""
    laudo = await LaudoService(user_id).get(laudo_id)
    if not laudo:
        return
    from pipeline.index import index_laudos
    await index_laudos([{
        "content":       laudo["laudo"],
        "source_name":   f"aprovado_{laudo_id[:8]}",
        "especialidade": laudo["especialidade"],
        "tipo_laudo":    laudo.get("tipo_laudo", ""),
        "aprovado":      True,
    }])
    logger.info("[Re-indexação] Laudo re-indexado", extra={"laudo_id": laudo_id})


async def _ingerir_laudo_repositorio(
    job_id: str, url: str, filename: str,
    especialidade: str, tipo_laudo: str, user_id: str,
) -> None:
    from pipeline.run_pipeline import ingerir_laudo
    await ingerir_laudo(url, filename, especialidade, tipo_laudo, user_id)
    logger.info("[Ingestão] Laudo ingerido", extra={"job_id": job_id})


async def _memorizar_correcao(laudo_id: str, user_id: str, correcoes: str) -> None:
    """Mem0 aprende com as correções que o médico fez no laudo."""
    laudo = await LaudoService(user_id).get(laudo_id)
    if not laudo or not laudo.get("laudo_editado"):
        return
    mem = LaudifierMemory()
    await mem.memorizar_correcao(
        medico_id=user_id,
        laudo_original=laudo.get("laudo", ""),
        laudo_editado=laudo["laudo_editado"],
        especialidade=laudo.get("especialidade", ""),
    )
    logger.info("[Mem0] Correção memorizada", extra={"laudo_id": laudo_id})
