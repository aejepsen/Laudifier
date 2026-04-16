# backend/agents/laudo_agent.py
"""
Agente de Geração de Laudos Médicos — LangGraph + Mem0.

Fluxo com Memory 2.0:
1. Recupera memórias do médico (Mem0) — preferências, padrões, correções
2. Busca laudos de referência no Qdrant (RAG)
3. Decide estratégia: RAG ou fallback Claude
4. Injeta AMBOS contextos no prompt: memória Mem0 + laudos referência
5. Gera o laudo com streaming
6. Persiste a interação no Mem0 em background
"""

import os
import asyncio
from typing import AsyncGenerator, TypedDict
import anthropic
from langfuse.decorators import observe

from .search_agent             import LaudoSearchAgent
from ..services.prompt_service import load_system_prompt
from ..services.memory_service import LaudifierMemory

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
CONTEXT_RELEVANCE_THRESHOLD = 0.60


class LaudoState(TypedDict):
    solicitacao:     str
    especialidade:   str
    dados_clinicos:  dict
    laudos_ref:      list[dict]
    usar_contexto:   bool
    laudo_gerado:    str
    campos_faltando: list[str]
    tipo_geracao:    str


@observe(name="gerar-laudo")
async def gerar_laudo_stream(
    solicitacao:    str,
    especialidade:  str,
    dados_clinicos: dict,
    user_id:        str,
    paciente_id:    str | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Gera laudo médico com streaming SSE.
    Mem0 injeta contexto personalizado do médico automaticamente.
    """
    client    = anthropic.AsyncAnthropic()
    mem_svc   = LaudifierMemory()

    # ── 1. Recupera memórias do médico via Mem0 ───────────────────────────────
    contexto_mem0    = mem_svc.buscar_contexto_medico(user_id, solicitacao, especialidade)
    historico_paciente = ""
    if paciente_id:
        historico_paciente = mem_svc.buscar_historico_paciente(paciente_id, solicitacao)

    tem_memoria = bool(contexto_mem0 or historico_paciente)

    # ── 2. Busca laudos de referência (RAG) ───────────────────────────────────
    search    = LaudoSearchAgent()
    laudos_ref = await search.buscar_laudos_similares(
        query=solicitacao,
        especialidade=especialidade,
        top=5,
    )

    # ── 3. Decide estratégia ──────────────────────────────────────────────────
    score_max     = max((l.get("score", 0) for l in laudos_ref), default=0)
    usar_contexto = score_max >= CONTEXT_RELEVANCE_THRESHOLD
    tipo_geracao  = "rag" if usar_contexto else "fallback"

    # ── 4. Emite metadados para o frontend ────────────────────────────────────
    yield {
        "type":         "meta",
        "tipo_geracao": tipo_geracao,
        "laudos_ref":   len(laudos_ref),
        "score":        score_max,
        "tem_memoria":  tem_memoria,
    }

    # ── 5. Monta cabeçalho de status ──────────────────────────────────────────
    status_parts = []
    if usar_contexto:
        status_parts.append(
            f"📚 Usando {len(laudos_ref)} laudo(s) de referência (score: {score_max:.2f})"
        )
    else:
        status_parts.append(
            "🧠 Gerando com base em conhecimento clínico geral — sem referência no repositório."
        )
    if tem_memoria:
        status_parts.append("💾 Contexto personalizado do médico aplicado (Mem0).")

    yield {"type": "token", "text": "\n".join(status_parts) + "\n\n"}

    # ── 6. Monta prompt completo ──────────────────────────────────────────────
    prompt = _montar_prompt(
        solicitacao=solicitacao,
        especialidade=especialidade,
        dados_clinicos=dados_clinicos,
        contexto_mem0=contexto_mem0,
        historico_paciente=historico_paciente,
        laudos_ref=laudos_ref if usar_contexto else [],
    )

    system = load_system_prompt()

    # ── 7. Streaming Claude ───────────────────────────────────────────────────
    full_laudo = ""
    async with client.messages.stream(
        model=ANTHROPIC_MODEL,
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        async for token in stream.text_stream:
            full_laudo += token
            yield {"type": "token", "text": token}

    # ── 8. Emite fontes e conclusão ───────────────────────────────────────────
    campos_faltando = _extrair_campos_faltando(full_laudo)
    yield {
        "type":            "done",
        "tipo_geracao":    tipo_geracao,
        "laudos_ref":      [{"id": l["id"], "nome": l["source_name"], "score": l.get("score", 0)} for l in laudos_ref],
        "campos_faltando": campos_faltando,
        "laudo":           full_laudo,
        "tem_memoria":     tem_memoria,
    }

    # ── 9. Persiste no Mem0 em background ────────────────────────────────────
    asyncio.create_task(
        mem_svc.memorizar_interacao(
            medico_id=user_id,
            solicitacao=solicitacao,
            laudo=full_laudo,
            especialidade=especialidade,
            tipo_geracao=tipo_geracao,
            paciente_id=paciente_id,
        )
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _montar_prompt(
    solicitacao:       str,
    especialidade:     str,
    dados_clinicos:    dict,
    contexto_mem0:     str,
    historico_paciente: str,
    laudos_ref:        list[dict],
) -> str:
    """
    Monta o prompt completo com todas as camadas de contexto:
    1. Memória Mem0 do médico (preferências, padrões, correções)
    2. Histórico do paciente (exames anteriores via Mem0)
    3. Laudos de referência do repositório (RAG Qdrant)
    4. Solicitação atual do médico
    """
    secoes = [f"ESPECIALIDADE: {especialidade.upper()}"]

    # Camada 1 — Contexto Mem0 (preferências e padrões do médico)
    if contexto_mem0:
        secoes.append(
            "── CONTEXTO PERSONALIZADO DO MÉDICO (Mem0) ──\n"
            + contexto_mem0
        )

    # Camada 2 — Histórico do paciente (Mem0)
    if historico_paciente:
        secoes.append(
            "── HISTÓRICO DO PACIENTE ──\n"
            + historico_paciente
        )

    # Camada 3 — Dados do exame atual
    dados_str = _formatar_dados(dados_clinicos)
    if dados_str:
        secoes.append(f"── DADOS DO EXAME ──\n{dados_str}")

    # Camada 4 — Laudos de referência (RAG)
    if laudos_ref:
        refs = _formatar_refs(laudos_ref)
        secoes.append(f"── LAUDOS DE REFERÊNCIA DO REPOSITÓRIO ──\n{refs}")

    # Camada 5 — Solicitação do médico
    secoes.append(
        f"── SOLICITAÇÃO DO MÉDICO ──\n{solicitacao}\n\n"
        "Gere o laudo médico completo. "
        "Aplique as preferências do médico quando disponíveis. "
        "Identifique e liste ao final quaisquer campos que precisam ser preenchidos."
    )

    return "\n\n".join(secoes)


def _formatar_refs(laudos: list[dict]) -> str:
    parts = []
    for i, l in enumerate(laudos, 1):
        parts.append(
            f"[Ref {i} — {l.get('especialidade','')}/{l.get('tipo_laudo','')}, "
            f"score: {l.get('score',0):.2f}]\n{l['content'][:1200]}"
        )
    return "\n\n".join(parts)


def _formatar_dados(dados: dict) -> str:
    if not dados:
        return ""
    return "\n".join(f"  {k}: {v}" for k, v in dados.items() if v)


_formatar_dados_clinicos = _formatar_dados


def _extrair_campos_faltando(laudo: str) -> list[str]:
    import re
    return re.findall(r'\[([A-ZÁÉÍÓÚÂÊÔÃÕÇ\s/]+)\]', laudo)
