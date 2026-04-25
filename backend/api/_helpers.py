# backend/api/_helpers.py
"""Background tasks compartilhadas entre rotas (re-indexação, anonimização, mem0)."""
from __future__ import annotations

import logging
import re

from ..services.laudo_service import LaudoService
from ..services.memory_service import LaudifierMemory
from ._shared import storage

logger = logging.getLogger(__name__)


async def _re_indexar_laudo_aprovado(laudo_id: str, user_id: str) -> None:
    """
    Indexa laudo aprovado no Qdrant vinculado ao médico.
    Se o laudo foi gerado por fallback (sem RAG), também indexa no repositório geral
    para que futuras gerações de qualquer médico possam usá-lo como referência.
    Dados do paciente são removidos antes da indexação (privacidade).
    """
    laudo = await LaudoService(user_id).get(laudo_id)
    if not laudo:
        return

    texto = laudo.get("laudo_editado") or laudo["laudo"]
    texto_anonimizado = _anonimizar_laudo(texto)
    especialidade = laudo.get("especialidade", "")
    solicitacao   = laudo.get("solicitacao", "")

    from ..agents.search_agent import LaudoSearchAgent
    search = LaudoSearchAgent()

    await search.indexar_laudo_aprovado(
        laudo_id=laudo_id,
        medico_id=user_id,
        laudo_text=texto_anonimizado,
        especialidade=especialidade,
        solicitacao=solicitacao,
    )

    if laudo.get("tipo_geracao") == "fallback":
        await search.indexar_no_repositorio_geral(
            laudo_id=laudo_id,
            laudo_text=texto_anonimizado,
            especialidade=especialidade,
            solicitacao=solicitacao,
        )
        logger.info("[Re-indexação] Laudo fallback promovido ao repositório geral", extra={"laudo_id": laudo_id})

    logger.info("[Re-indexação] Laudo indexado para médico", extra={"laudo_id": laudo_id, "user_id": user_id})


def _anonimizar_laudo(texto: str) -> str:
    """
    Remove dados identificadores do paciente antes de indexar.
    Substitui nomes, datas, CRMs e outros dados pessoais por placeholders.
    """
    padroes = [
        (r'\b(?:Paciente|Nome)\s*:\s*.+',          'Paciente: [PACIENTE]'),
        (r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',           '[DATA]'),
        (r'\bCRM\s*[:\-]?\s*[\w\-/]+',              'CRM: [CRM]'),
        (r'\bDr[aA]?\.?\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+)*', 'Dr. [MÉDICO]'),
        (r'\[NOME DO PACIENTE\]',                   '[PACIENTE]'),
        (r'\[DATA DO EXAME\]',                      '[DATA]'),
        (r'\[CRM DO MÉDICO\]',                      '[CRM]'),
        (r'\[ASSINATURA\]',                         '[MÉDICO]'),
    ]
    for pattern, replacement in padroes:
        texto = re.sub(pattern, replacement, texto, flags=re.IGNORECASE)
    return texto


async def _ingerir_laudo_repositorio(
    job_id: str, url: str, filename: str,
    especialidade: str, tipo_laudo: str, user_id: str,
) -> None:
    from pipeline.run_pipeline import ingerir_laudo
    await ingerir_laudo(url, filename, especialidade, tipo_laudo, user_id)
    storage.delete_document(url)
    logger.info("[Ingestão] Laudo ingerido e arquivo original removido do storage", extra={"job_id": job_id})


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
