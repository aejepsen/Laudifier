# backend/api/memory_routes.py
"""
Endpoints da camada Mem0 — expostos ao frontend Angular.
O médico pode visualizar e gerenciar as memórias que o sistema aprendeu sobre ele.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from .auth import verify_token, UserContext
from ..services.memory_service import LaudifierMemory

router = APIRouter(prefix="/memoria", tags=["memoria"])
logger = logging.getLogger(__name__)


class DeleteMemoriaRequest(BaseModel):
    memory_id: str


@router.get("/")
async def listar_memorias(user: UserContext = Depends(verify_token)):
    """
    Retorna todas as memórias que o Mem0 aprendeu sobre este médico.
    Exibido na UI para transparência e gerenciamento.
    """
    mem   = LaudifierMemory()
    itens = mem.listar_memorias_medico(user.id)
    return {
        "total":    len(itens),
        "memorias": [
            {
                "id":         m.get("id"),
                "conteudo":   m.get("memory", ""),
                "categorias": m.get("categories", []),
                "criada_em":  m.get("created_at", ""),
                "score":      m.get("score"),
            }
            for m in itens
        ],
    }


@router.delete("/{memory_id}")
async def deletar_memoria(
    memory_id: str,
    user:      UserContext = Depends(verify_token),
):
    """Remove uma memória específica — verifica ownership antes de deletar."""
    mem   = LaudifierMemory()
    # Verifica que a memória pertence ao usuário autenticado (previne IDOR)
    todas = mem.listar_memorias_medico(user.id)
    ids_do_usuario = {m.get("id") for m in todas}
    if memory_id not in ids_do_usuario:
        raise HTTPException(status_code=404, detail="Memória não encontrada")

    mem.deletar_memoria(memory_id)
    logger.info("[Mem0] Memória deletada", extra={"user_id": user.id, "memory_id": memory_id})
    return {"status": "deleted", "memory_id": memory_id}


@router.delete("/")
async def limpar_todas_memorias(user: UserContext = Depends(verify_token)):
    """
    Remove TODAS as memórias do médico.
    Útil para LGPD/GDPR ou para "resetar" o aprendizado.
    """
    mem = LaudifierMemory()
    mem.limpar_memorias_medico(user.id)
    logger.info("[Mem0] Todas as memórias removidas", extra={"user_id": user.id})
    return {"status": "cleared", "user_id": user.id}


@router.get("/preview")
async def preview_contexto(
    especialidade: str,
    solicitacao:   str = "laudo de exame",
    user:          UserContext = Depends(verify_token),
):
    """
    Prévia do contexto Mem0 que será injetado no próximo laudo.
    Permite ao médico ver o que o sistema "sabe" sobre suas preferências.
    """
    mem      = LaudifierMemory()
    contexto = mem.buscar_contexto_medico(user.id, solicitacao, especialidade)
    return {
        "especialidade": especialidade,
        "contexto":      contexto or "Nenhuma memória relevante encontrada ainda.",
        "tem_contexto":  bool(contexto),
    }
