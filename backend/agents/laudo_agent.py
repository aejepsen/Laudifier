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
import re
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


_MEM0_TIMEOUT = 8.0
_SPLIT_MARKER = "── SOLICITAÇÃO DO MÉDICO ──"


async def _resolver_contexto_mem0(
    mem_svc:       "LaudifierMemory",
    user_id:       str,
    solicitacao:   str,
    especialidade: str,
    paciente_id:   str | None,
) -> tuple[str, str, bool]:
    """Busca contexto do médico e histórico do paciente no Mem0 com timeout gracioso."""
    contexto_mem0, historico_paciente = "", ""
    try:
        contexto_mem0 = await asyncio.wait_for(
            asyncio.to_thread(mem_svc.buscar_contexto_medico, user_id, solicitacao, especialidade),
            timeout=_MEM0_TIMEOUT,
        )
    except (asyncio.TimeoutError, ConnectionError, RuntimeError):
        pass
    if paciente_id:
        try:
            historico_paciente = await asyncio.wait_for(
                asyncio.to_thread(mem_svc.buscar_historico_paciente, paciente_id, solicitacao),
                timeout=_MEM0_TIMEOUT,
            )
        except (asyncio.TimeoutError, ConnectionError, RuntimeError):
            pass
    return contexto_mem0, historico_paciente, bool(contexto_mem0 or historico_paciente)


async def _buscar_refs_rag(
    search:        LaudoSearchAgent,
    user_id:       str,
    solicitacao:   str,
    especialidade: str,
) -> list[dict]:
    """Busca laudos do próprio médico (prioridade) + laudos gerais, sem duplicatas."""
    laudos_proprios, laudos_gerais = await asyncio.gather(
        search.buscar_laudos_do_medico(user_id, solicitacao, especialidade, top=3),
        search.buscar_laudos_similares(solicitacao, especialidade, top=5),
    )
    ids_proprios = {l["id"] for l in laudos_proprios}
    return laudos_proprios + [l for l in laudos_gerais if l["id"] not in ids_proprios]


def _status_header(usar_contexto: bool, n_refs: int, score_max: float, tem_memoria: bool) -> str:
    if usar_contexto:
        head = f"📚 Usando {n_refs} laudo(s) de referência (score: {score_max:.2f})"
    else:
        head = "🧠 Gerando com base em conhecimento clínico geral — sem referência no repositório."
    if tem_memoria:
        head += "\n💾 Contexto personalizado do médico aplicado (Mem0)."
    return head + "\n\n"


def _build_user_content(prompt: str) -> list[dict]:
    """Divide o prompt em parte cacheável (contexto) e dinâmica (solicitação) para prompt caching."""
    if _SPLIT_MARKER in prompt:
        ctx_part, query_part = prompt.split(_SPLIT_MARKER, 1)
        query_part = _SPLIT_MARKER + query_part
    else:
        ctx_part, query_part = "", prompt
    blocks: list[dict] = []
    if ctx_part.strip():
        blocks.append({"type": "text", "text": ctx_part.rstrip(), "cache_control": {"type": "ephemeral"}})
    blocks.append({"type": "text", "text": query_part})
    return blocks


async def _stream_claude(
    client:       anthropic.AsyncAnthropic,
    system:       str,
    user_content: list[dict],
    max_tokens:   int = 4000,
) -> AsyncGenerator[tuple[str, str], None]:
    """Emite (token, full_laudo_acumulado) a cada token streamed do Claude."""
    full = ""
    async with client.messages.stream(
        model=ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_content}],
    ) as stream:
        async for token in stream.text_stream:
            full += token
            yield token, full


def _finalizar_laudo(full_laudo: str, dados_clinicos: dict) -> tuple[str, list[str]]:
    """Aplica filtros finais e retorna (laudo_final, campos_faltando)."""
    laudo = _filtrar_metadata(full_laudo)
    laudo = _preencher_assinatura(
        laudo,
        dados_clinicos.get("medico", ""),
        dados_clinicos.get("medico_crm", ""),
    )
    return laudo, _extrair_campos_faltando(laudo)


def _persistir_mem0_bg(
    mem_svc:       "LaudifierMemory",
    user_id:       str,
    solicitacao:   str,
    laudo:         str,
    especialidade: str,
    tipo_geracao:  str,
    paciente_id:   str | None,
) -> None:
    """Dispara persistência no Mem0 em background com handler — sem fire-and-forget silencioso."""
    task = asyncio.create_task(
        mem_svc.memorizar_interacao(
            medico_id=user_id,
            solicitacao=solicitacao,
            laudo=laudo,
            especialidade=especialidade,
            tipo_geracao=tipo_geracao,
            paciente_id=paciente_id,
        )
    )
    def _log_err(t: asyncio.Task) -> None:
        if (exc := t.exception()) is not None:
            import logging
            logging.getLogger(__name__).warning("memorizar_interacao falhou: %s", exc)
    task.add_done_callback(_log_err)


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
    Orquestra: Mem0 (contexto médico + paciente) + RAG Qdrant + Claude streaming.
    """
    client  = anthropic.AsyncAnthropic()
    mem_svc = LaudifierMemory()

    contexto_mem0, historico_paciente, tem_memoria = await _resolver_contexto_mem0(
        mem_svc, user_id, solicitacao, especialidade, paciente_id,
    )

    laudos_ref    = await _buscar_refs_rag(LaudoSearchAgent(), user_id, solicitacao, especialidade)
    score_max     = max((l.get("score", 0) for l in laudos_ref), default=0)
    usar_contexto = score_max >= CONTEXT_RELEVANCE_THRESHOLD
    tipo_geracao  = "rag" if usar_contexto else "fallback"

    yield {
        "type": "meta", "tipo_geracao": tipo_geracao, "laudos_ref": len(laudos_ref),
        "score": score_max, "tem_memoria": tem_memoria,
    }
    yield {"type": "token", "text": _status_header(usar_contexto, len(laudos_ref), score_max, tem_memoria)}

    prompt = _montar_prompt(
        solicitacao=solicitacao,
        especialidade=especialidade,
        dados_clinicos=dados_clinicos,
        contexto_mem0=contexto_mem0,
        historico_paciente=historico_paciente,
        laudos_ref=laudos_ref if usar_contexto else [],
    )

    full_laudo = ""
    async for token, full_laudo in _stream_claude(client, load_system_prompt(), _build_user_content(prompt)):
        yield {"type": "token", "text": token}

    full_laudo, campos_faltando = _finalizar_laudo(full_laudo, dados_clinicos)
    yield {
        "type": "done", "tipo_geracao": tipo_geracao,
        "laudos_ref":      [{"id": l["id"], "nome": l["source_name"], "score": l.get("score", 0)} for l in laudos_ref],
        "campos_faltando": campos_faltando,
        "laudo":           full_laudo,
        "tem_memoria":     tem_memoria,
    }

    _persistir_mem0_bg(mem_svc, user_id, solicitacao, full_laudo, especialidade, tipo_geracao, paciente_id)


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

    # ── Edição de linha específica: Claude corrige só aquela linha ───────────
    # Quando médico diz "14 frontal direita", extraímos a linha 14 e pedimos
    # ao Claude para preencher/corrigir apenas ela — preserva o restante do texto.
    linha_ref = _extrair_linha_referenciada(laudo_atual, achados)
    if linha_ref is not None:
        num_linha, texto_linha, instrucao = linha_ref
        client = anthropic.AsyncAnthropic()
        prompt_linha = (
            f"Linha atual do laudo:\n{texto_linha}\n\n"
            f"Instrução do médico: {instrucao}\n\n"
            "Retorne APENAS o texto corrigido desta linha, incorporando a instrução "
            "com terminologia radiológica precisa. Sem explicações, sem numeração."
        )
        resp = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt_linha}],
        )
        linha_corrigida = resp.content[0].text.strip()
        laudo_corrigido = _substituir_linha_texto(laudo_atual, num_linha, linha_corrigida)
        CHUNK = 200
        for i in range(0, len(laudo_corrigido), CHUNK):
            yield {"type": "token", "text": laudo_corrigido[i:i + CHUNK]}
        laudo_corrigido = _filtrar_metadata(laudo_corrigido)
        campos_faltando = _extrair_campos_faltando(laudo_corrigido)
        yield {"type": "done", "campos_faltando": campos_faltando, "laudo": laudo_corrigido}
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
    ) as stream:
        async for token in stream.text_stream:
            full_laudo += token
            yield {"type": "token", "text": token}

    full_laudo = _filtrar_metadata(full_laudo)
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
    dados_bloco = f"── DADOS DO EXAME E MÉDICO ──\n{dados_str}\n\n" if dados_str else ""

    medico_nome = dados_paciente.get("medico", "")
    medico_crm  = dados_paciente.get("medico_crm", "")
    medico_instrucao = (
        f"5. Preencha [NOME DO MÉDICO] com '{medico_nome}' e [CRM DO MÉDICO] com '{medico_crm}'. "
        "Apenas [ASSINATURA] deve permanecer como placeholder."
    ) if medico_nome else (
        "5. Apenas [NOME DO MÉDICO], [CRM DO MÉDICO] e [ASSINATURA] devem permanecer como placeholder."
    )

    prompt = (
        f"ESPECIALIDADE: {especialidade.upper()}\n\n"
        f"{dados_bloco}"
        f"── LAUDO COM ACHADOS PREENCHIDOS ──\n{laudo_atual}\n\n"
        "Com base nos achados descritos acima:\n"
        "1. Gere ou reescreva a seção IMPRESSÃO DIAGNÓSTICA de forma objetiva e conclusiva.\n"
        "2. Se dados do paciente foram fornecidos, preencha [NOME DO PACIENTE], [DATA DE NASCIMENTO], [SEXO] e similares.\n"
        "3. Preencha [INDICAÇÃO CLÍNICA] com o valor de 'indicacao' se fornecido.\n"
        "4. Retorne o laudo COMPLETO e FINAL, sem campos de achados em branco.\n"
        f"{medico_instrucao}"
    )

    system = load_system_prompt()
    full_laudo = ""
    async with client.messages.stream(
        model=ANTHROPIC_MODEL,
        max_tokens=3000,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        async for token in stream.text_stream:
            full_laudo += token
            yield {"type": "token", "text": token}

    full_laudo = _filtrar_metadata(full_laudo)
    full_laudo = _preencher_assinatura(
        full_laudo,
        dados_paciente.get("medico", ""),
        dados_paciente.get("medico_crm", ""),
    )
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
        secoes.append(f"── DADOS DO EXAME E MÉDICO ──\n{dados_str}")

    # Instrução explícita de preenchimento de campos do médico
    medico_nome = dados_clinicos.get("medico", "")
    medico_crm  = dados_clinicos.get("medico_crm", "")
    if medico_nome or medico_crm:
        instrucao = "IMPORTANTE: No laudo final, preencha automaticamente:\n"
        if medico_nome: instrucao += f"  - [NOME DO MÉDICO] → {medico_nome}\n"
        if medico_crm:  instrucao += f"  - [CRM DO MÉDICO] → CRM {medico_crm}\n"
        instrucao += "  - [INDICAÇÃO CLÍNICA] → usar valor de 'indicacao' acima\n"
        instrucao += "Apenas [ASSINATURA] deve permanecer como placeholder."
        secoes.append(instrucao)

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
        origem = "⭐ LAUDO DO PRÓPRIO MÉDICO" if l.get("source") == "medico_aprovado" \
                 else f"{l.get('especialidade','')}/{l.get('tipo_laudo','')}"
        parts.append(
            f"[Ref {i} — {origem}, score: {l.get('score',0):.2f}]\n{l['content'][:1200]}"
        )
    return "\n\n".join(parts)


def _formatar_dados(dados: dict) -> str:
    if not dados:
        return ""
    return "\n".join(f"  {k}: {v}" for k, v in dados.items() if v)


_formatar_dados_clinicos = _formatar_dados


def _extrair_linha_referenciada(laudo: str, achados_normalizado: str) -> tuple[int, str, str] | None:
    """
    Se achados é 'linha N: instrução', retorna (num, texto_atual_da_linha, instrução).
    Retorna None se não for referência de linha.
    """
    import re
    m = re.match(r'^linha\s+(\d+):\s+(.+)', achados_normalizado.strip(), re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    num_alvo  = int(m.group(1))
    instrucao = m.group(2).strip()
    linhas    = laudo.split('\n')
    contador  = 0
    for linha in linhas:
        if linha.strip():
            contador += 1
            if contador == num_alvo:
                return (num_alvo, linha, instrucao)
    return None


def _substituir_linha_texto(laudo: str, num_alvo: int, novo_texto: str) -> str:
    """Substitui a N-ésima linha não-vazia pelo novo_texto."""
    linhas  = laudo.split('\n')
    contador = 0
    for i, linha in enumerate(linhas):
        if linha.strip():
            contador += 1
            if contador == num_alvo:
                linhas[i] = novo_texto
                return '\n'.join(linhas)
    return laudo


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


_META_RE = __import__('re').compile(
    r'^\s*[✅\-\*]?\s*'
    r'(Tipo de Laudo|Referência utilizada|Status|score\s+[\d.]+)',
    __import__('re').IGNORECASE,
)

def _filtrar_metadata(laudo: str) -> str:
    """Remove linhas de metadados do sistema que o modelo inclui incorretamente."""
    linhas = laudo.splitlines()
    filtradas = [l for l in linhas if not _META_RE.match(l)]
    return "\n".join(filtradas).rstrip()


_RE_PLACEHOLDER_ASSINATURA = re.compile(r'^\[ASSINATURA[^\]]*\]\s*$\n?', re.MULTILINE)
_RE_PLACEHOLDER_CRM = re.compile(r'\[CRM DO MÉDICO\]')
_RE_LINHA_CRM_VAZIA = re.compile(r'^CRM:\s*$', re.MULTILINE)
_RE_LINHA_UNDERSCORES = re.compile(r'^_{5,}\s*$')
_RE_QUEBRAS_EXCESSIVAS = re.compile(r'\n{3,}')


def _remover_placeholder_assinatura(laudo: str) -> str:
    return _RE_PLACEHOLDER_ASSINATURA.sub('', laudo)


def _substituir_placeholders_medico(laudo: str, nome: str, crm: str) -> str:
    if nome:
        laudo = laudo.replace('[NOME DO MÉDICO]', nome)
    if crm:
        laudo = _RE_PLACEHOLDER_CRM.sub(crm, laudo)
        laudo = _RE_LINHA_CRM_VAZIA.sub(f'CRM: {crm}', laudo)
    return laudo


def _proximo_conteudo(linhas: list[str], inicio: int) -> str:
    j = inicio
    while j < len(linhas) and not linhas[j].strip():
        j += 1
    return linhas[j].strip() if j < len(linhas) else ''


def _inserir_assinatura_apos_underscores(laudo: str, nome: str, crm: str) -> str:
    if not (nome and '___' in laudo):
        return laudo
    linhas = laudo.splitlines()
    resultado: list[str] = []
    for i, linha in enumerate(linhas):
        resultado.append(linha)
        if not _RE_LINHA_UNDERSCORES.match(linha):
            continue
        if nome in _proximo_conteudo(linhas, i + 1):
            continue
        resultado.append(nome)
        if crm:
            resultado.append(f'CRM: {crm}')
    return '\n'.join(resultado)


def _preencher_assinatura(laudo: str, medico_nome: str, medico_crm: str) -> str:
    """
    Preenche automaticamente o bloco de assinatura com nome e CRM do médico.
    Remove placeholders incorretos como [ASSINATURA DO MÉDICO — email].
    """
    laudo = _remover_placeholder_assinatura(laudo)
    laudo = _substituir_placeholders_medico(laudo, medico_nome, medico_crm)
    laudo = _inserir_assinatura_apos_underscores(laudo, medico_nome, medico_crm)
    laudo = _RE_QUEBRAS_EXCESSIVAS.sub('\n\n', laudo)
    return laudo.rstrip()
