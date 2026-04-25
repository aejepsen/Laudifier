# backend/api/routes/dashboard.py
"""Estatísticas administrativas."""
import logging

from fastapi import APIRouter, Depends, HTTPException

from ...services.laudo_service import LaudoService
from ..auth import UserContext, verify_token

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/dashboard/stats")
async def dashboard_stats(user: UserContext = Depends(verify_token)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")
    try:
        svc = LaudoService(user.id)
        return await svc.get_stats()
    except Exception:
        logger.error("[Dashboard] Erro ao buscar stats", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao carregar estatísticas")
