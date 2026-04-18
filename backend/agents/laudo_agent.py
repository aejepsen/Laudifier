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

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
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

    # ── 1. Recupera memórias do médico via Mem0 (non-blocking com timeout) ──────
    # Mem0 usa sentence-transformers sincronamente — wrapping em thread evita
    # bloquear o event loop; timeout de 8s garante fallback gracioso se lento.
    try:
        contexto_mem0 = await asyncio.wait_for(
            asyncio.to_thread(mem_svc.buscar_contexto_medico, user_id, solicitacao, especialidade),
            timeout=8.0,
        )
    except Exception:
        contexto_mem0 = ""

    historico_paciente = ""
    if paciente_id:
        try:
            historico_paciente = await asyncio.wait_for(
                asyncio.to_thread(mem_svc.buscar_historico_paciente, paciente_id, solicitacao),
                timeout=8.0,
            )
        except Exception:
            historico_paciente = ""

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

    # ── 7. Streaming Claude com prompt caching ────────────────────────────────
    # Divide o prompt em parte cacheável (contexto RAG + mem0) e dinâmica (solicitação)
    _SPLIT = "── SOLICITAÇÃO DO MÉDICO ──"
    if _SPLIT in prompt:
        ctx_part, query_part = prompt.split(_SPLIT, 1)
        query_part = _SPLIT + query_part
    else:
        ctx_part, query_part = "", prompt

    user_content: list[dict] = []
    if ctx_part.strip():
        user_content.append({
            "type": "text",
            "text": ctx_part.rstrip(),
            "cache_control": {"type": "ephemeral"},  # cache contexto RAG + mem0
        })
    user_content.append({"type": "text", "text": query_part})

    full_laudo = ""
    async with client.messages.stream(
        model=ANTHROPIC_MODEL,
        max_tokens=4000,
        system=[{
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},  # cache system prompt
        }],
        messages=[{"role": "user", "content": user_content}],
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
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


@observe(name="corrigir-laudo")
async def corrigir_laudo_stream(
    laudo_atual:  str,
    achados:      str,
    especialidade: str,
    user_id:      str,
) -> AsyncGenerator[dict, None]:
    """
    Etapa 3 — Correção assistida por RAG.
    Recebe o laudo atual + achados do médico em linguagem livre.
    Usa RAG de frases especializadas para reescrever em terminologia radiológica.
    """
    # Normaliza instrução: "16 texto" → "linha 16: texto"
    achados = _normalizar_instrucao_linhas(achados)

    # ── Substituição determinística de linha ──────────────────────────────────
    # Se o médico referenciou uma linha específica, substituímos diretamente
    # sem passar pelo Claude (evita que ele reescreva o laudo inteiro).
    laudo_direto = _substituir_linha(laudo_atual, achados)
    if laudo_direto is not None:
        # Emite o laudo corrigido em chunks para manter a UX de streaming
        CHUNK = 200
        for i in range(0, len(laudo_direto), CHUNK):
            yield {"type": "token", "text": laudo_direto[i:i + CHUNK]}
        campos_faltando = _extrair_campos_faltando(laudo_direto)
        yield {"type": "done", "campos_faltando": campos_faltando, "laudo": laudo_direto}
        return

    # ── Instrução geral: usa Claude + RAG ─────────────────────────────────────
    client = anthropic.AsyncAnthropic()
    search = LaudoSearchAgent()

    laudos_ref = await search.buscar_laudos_similares(
        query=achados,
        especialidade=especialidade,
        top=5,
    )

    refs_str = ""
    if laudos_ref:
        refs_str = "\n\n── FRASES DE REFERÊNCIA DO REPOSITÓRIO ──\n"
        for i, l in enumerate(laudos_ref, 1):
            refs_str += f"[Ref {i}]\n{l['content'][:800]}\n\n"

    prompt = (
        f"ESPECIALIDADE: {especialidade.upper()}\n\n"
        f"── LAUDO ATUAL ──\n{laudo_atual}\n\n"
        f"{refs_str}"
        f"── INSTRUÇÃO DO MÉDICO ──\n{achados}\n\n"
        "Incorpore os achados do médico com terminologia radiológica precisa. "
        "Mantenha a estrutura do laudo atual. "
        "Use as frases de referência como vocabulário — não copie placeholders. "
        "Retorne o laudo COMPLETO e corrigido."
    )

    system = load_system_prompt()
    full_laudo = ""
    async with client.messages.stream(
        model=ANTHROPIC_MODEL,
        max_tokens=3000,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
    ) as stream:
        async for token in stream.text_stream:
            full_laudo += token
            yield {"type": "token", "text": token}

    campos_faltando = _extrair_campos_faltando(full_laudo)
    yield {"type": "done", "campos_faltando": campos_faltando, "laudo": full_laudo}

    asyncio.create_task(
        LaudifierMemory().memorizar_interacao(
            medico_id=user_id,
            solicitacao=f"correção: {achados[:200]}",
            laudo=full_laudo,
            especialidade=especialidade,
            tipo_geracao="correcao",
        )
    )


@observe(name="gerar-conclusao")
async def gerar_conclusao_stream(
    laudo_atual:    str,
    dados_paciente: dict,
    especialidade:  str,
) -> AsyncGenerator[dict, None]:
    """
    Etapa 4 — Geração de conclusão/impressão diagnóstica.
    Recebe o laudo com achados preenchidos e gera a IMPRESSÃO DIAGNÓSTICA.
    Substitui dados do paciente quando fornecidos.
    """
    client = anthropic.AsyncAnthropic()

    dados_str = "\n".join(f"  {k}: {v}" for k, v in dados_paciente.items() if v)
    dados_bloco = f"── DADOS DO PACIENTE ──\n{dados_str}\n\n" if dados_str else ""

    prompt = (
        f"ESPECIALIDADE: {especialidade.upper()}\n\n"
        f"{dados_bloco}"
        f"── LAUDO COM ACHADOS PREENCHIDOS ──\n{laudo_atual}\n\n"
        "Com base nos achados descritos acima:\n"
        "1. Gere ou reescreva a seção IMPRESSÃO DIAGNÓSTICA de forma objetiva e conclusiva.\n"
        "2. Se dados do paciente foram fornecidos, preencha [NOME DO PACIENTE], [DATA DO EXAME] e similares.\n"
        "3. Retorne o laudo COMPLETO e FINAL, pronto para assinatura do médico.\n"
        "4. NUNCA deixe campos vazios nas seções de achados — use o que está preenchido.\n"
        "5. Apenas [CRM DO MÉDICO] e [ASSINATURA] devem permanecer como placeholder."
    )

    system = load_system_prompt()
    full_laudo = ""
    async with client.messages.stream(
        model=ANTHROPIC_MODEL,
        max_tokens=3000,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
        extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
    ) as stream:
        async for token in stream.text_stream:
            full_laudo += token
            yield {"type": "token", "text": token}

    campos_faltando = _extrair_campos_faltando(full_laudo)
    yield {"type": "done", "campos_faltando": campos_faltando, "laudo": full_laudo}


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


def _substituir_linha(laudo: str, achados_normalizado: str) -> str | None:
    """
    Se achados_normalizado é 'linha N: novo texto', substitui a N-ésima linha
    não-vazia do laudo de forma determinística e retorna o laudo modificado.
    Retorna None se não for uma referência de linha.
    """
    import re
    m = re.match(r'^linha\s+(\d+):\s+(.+)', achados_normalizado.strip(), re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    num_alvo = int(m.group(1))
    novo_texto = m.group(2).strip()

    linhas = laudo.split('\n')
    contador = 0
    for i, linha in enumerate(linhas):
        if linha.strip():
            contador += 1
            if contador == num_alvo:
                linhas[i] = novo_texto
                return '\n'.join(linhas)
    return None  # número de linha fora do intervalo


def _normalizar_instrucao_linhas(achados: str) -> str:
    """
    Normaliza referências de linha para formato canônico 'linha N: texto'.
    Aceita fala natural sem keyword 'linha' ou sem dois-pontos:
      "16 a lesão..."          → "linha 16: a lesão..."
      "16: a lesão..."         → "linha 16: a lesão..."
      "linha 16 a lesão..."    → "linha 16: a lesão..."
      "linha 16: a lesão..."   → sem mudança
    """
    import re
    # Detecta início: (opcional "linha ") + dígitos + (opcional ":") + espaço + texto
    pattern = r'^(?:linha\s+)?(\d+)\s*:?\s+(.+)'
    m = re.match(pattern, achados.strip(), re.IGNORECASE | re.DOTALL)
    if m:
        return f"linha {m.group(1)}: {m.group(2).strip()}"
    return achados


def _extrair_campos_faltando(laudo: str) -> list[str]:
    import re
    return re.findall(r'\[([A-ZÁÉÍÓÚÂÊÔÃÕÇ\s/]+)\]', laudo)
