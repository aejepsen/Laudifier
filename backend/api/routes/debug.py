# backend/api/routes/debug.py
"""
Endpoints de diagnóstico — admin only. Não expor a usuários comuns.

`/debug/profile` faz amostragem do processo por N segundos via pyinstrument
e devolve flame graph HTML. Use durante carga sintética para identificar
hotspots em CPU.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from ..auth import UserContext, verify_token

logger = logging.getLogger(__name__)
router = APIRouter()

_MAX_DURATION_SEC = 30


@router.get("/debug/profile", response_class=HTMLResponse)
async def profile_processo(
    duration: int = Query(default=5, ge=1, le=_MAX_DURATION_SEC),
    user:     UserContext = Depends(verify_token),
):
    """
    Amostragem CPU por `duration` segundos. Apenas role 'admin'.
    Retorna flame graph HTML (pyinstrument) — abrir no browser.

    Uso típico: dispare carga sintética em paralelo (ex.: locust),
    chame este endpoint para capturar onde o processo está gastando tempo.
    """
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Apenas administradores")

    try:
        from pyinstrument import Profiler
    except ImportError:
        raise HTTPException(status_code=501, detail="pyinstrument não instalado")

    profiler = Profiler(async_mode="enabled")
    profiler.start()
    try:
        await asyncio.sleep(duration)
    finally:
        profiler.stop()

    logger.info("[Debug] Profile capturado por %ds (user=%s)", duration, user.id)
    return profiler.output_html()
