"""Cobertura de helpers + orquestração de laudo_agent."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from backend.agents import laudo_agent as la


# ── _formatar_dados / _formatar_refs ─────────────────────────────────────────

def test_formatar_dados_vazio():
    assert la._formatar_dados({}) == ""


def test_formatar_dados_filtra_falsy():
    out = la._formatar_dados({"a": "1", "b": "", "c": None, "d": "ok"})
    assert "a: 1" in out
    assert "d: ok" in out
    assert "b:" not in out
    assert "c:" not in out


def test_formatar_refs_marca_proprio_medico():
    refs = [
        {"source": "medico_aprovado", "content": "X" * 100, "score": 0.9, "id": "a"},
        {"especialidade": "rad", "tipo_laudo": "rx", "content": "Y" * 100, "score": 0.7, "id": "b"},
    ]
    out = la._formatar_refs(refs)
    assert "PRÓPRIO MÉDICO" in out
    assert "rad/rx" in out
    assert "0.90" in out


def test_formatar_refs_trunca_em_1200():
    long = "z" * 5000
    refs = [{"content": long, "score": 0.8, "id": "x"}]
    out = la._formatar_refs(refs)
    assert "z" * 1200 in out
    assert "z" * 1201 not in out


# ── _extrair_campos_faltando ─────────────────────────────────────────────────

def test_extrair_campos_faltando_basico():
    laudo = "Paciente: [NOME DO PACIENTE]. CRM: [CRM DO MÉDICO]."
    campos = la._extrair_campos_faltando(laudo)
    assert "NOME DO PACIENTE" in campos
    assert "CRM DO MÉDICO" in campos


def test_extrair_campos_faltando_sem_placeholders():
    assert la._extrair_campos_faltando("Laudo limpo.") == []


# ── _filtrar_metadata ────────────────────────────────────────────────────────

def test_filtrar_metadata_remove_linhas_de_status():
    laudo = (
        "ACHADOS: normal.\n"
        "Tipo de Laudo: RX\n"
        "✅ Status: ok\n"
        "- Referência utilizada: x\n"
        "IMPRESSÃO: clara.\n"
    )
    out = la._filtrar_metadata(laudo)
    assert "Tipo de Laudo" not in out
    assert "Status" not in out
    assert "Referência utilizada" not in out
    assert "ACHADOS" in out
    assert "IMPRESSÃO" in out


def test_filtrar_metadata_preserva_corpo():
    assert la._filtrar_metadata("ACHADOS:\nNormal.") == "ACHADOS:\nNormal."


# ── _preencher_assinatura ────────────────────────────────────────────────────

def test_preencher_assinatura_substitui_placeholders():
    laudo = "Laudo.\n[NOME DO MÉDICO]\n[CRM DO MÉDICO]"
    out = la._preencher_assinatura(laudo, "Dr. House", "12345/SP")
    assert "Dr. House" in out
    assert "12345/SP" in out
    assert "[NOME DO MÉDICO]" not in out


def test_preencher_assinatura_remove_placeholder_assinatura():
    laudo = "Conteúdo.\n[ASSINATURA DO MÉDICO — email]\nFim."
    out = la._preencher_assinatura(laudo, "", "")
    assert "[ASSINATURA" not in out


def test_preencher_assinatura_insere_apos_underscores():
    laudo = "Conclusão.\n_______________\n"
    out = la._preencher_assinatura(laudo, "Dr. X", "999/RJ")
    linhas = out.splitlines()
    idx = next(i for i, l in enumerate(linhas) if l.startswith("___"))
    # próxima linha não-vazia deve ter o nome
    assert "Dr. X" in linhas[idx + 1]


def test_preencher_assinatura_preenche_crm_vazio():
    laudo = "Texto.\nCRM: \nFim."
    out = la._preencher_assinatura(laudo, "", "8888/MG")
    assert "CRM: 8888/MG" in out


def test_preencher_assinatura_collapsa_linhas_vazias():
    laudo = "A\n\n\n\n\nB"
    out = la._preencher_assinatura(laudo, "", "")
    assert "\n\n\n" not in out


# ── _normalizar_instrucao_linhas ─────────────────────────────────────────────

@pytest.mark.parametrize("inp,expected", [
    ("16 a lesão", "linha 16: a lesão"),
    ("16: a lesão", "linha 16: a lesão"),
    ("linha 16 a lesão", "linha 16: a lesão"),
    ("linha 16: a lesão", "linha 16: a lesão"),
])
def test_normalizar_instrucao_formatos(inp, expected):
    assert la._normalizar_instrucao_linhas(inp) == expected


def test_normalizar_instrucao_sem_match_passa():
    assert la._normalizar_instrucao_linhas("texto livre") == "texto livre"


# ── _extrair_linha_referenciada / _substituir_linha_texto ────────────────────

def test_extrair_linha_referenciada_acha():
    laudo = "Linha um\nLinha dois\nLinha três"
    out = la._extrair_linha_referenciada(laudo, "linha 2: nova")
    assert out == (2, "Linha dois", "nova")


def test_extrair_linha_referenciada_pula_vazias():
    laudo = "L1\n\nL2\n\nL3"
    out = la._extrair_linha_referenciada(laudo, "linha 3: nova")
    assert out[0] == 3
    assert out[1] == "L3"


def test_extrair_linha_referenciada_fora_do_alcance():
    assert la._extrair_linha_referenciada("L1\nL2", "linha 99: x") is None


def test_extrair_linha_referenciada_nao_match():
    assert la._extrair_linha_referenciada("L1", "instrução genérica") is None


def test_substituir_linha_texto():
    laudo = "L1\nL2\nL3"
    out = la._substituir_linha_texto(laudo, 2, "NOVA")
    assert out == "L1\nNOVA\nL3"


def test_substituir_linha_texto_fora_alcance():
    laudo = "L1"
    assert la._substituir_linha_texto(laudo, 99, "X") == laudo


def test_substituir_linha_combinado():
    laudo = "A\nB\nC"
    out = la._substituir_linha(laudo, "linha 2: novo")
    assert out == "A\nnovo\nC"


def test_substituir_linha_sem_match_retorna_none():
    assert la._substituir_linha("A\nB", "instrução livre") is None


def test_substituir_linha_fora_alcance_retorna_none():
    assert la._substituir_linha("A\nB", "linha 99: x") is None


# ── _build_user_content ──────────────────────────────────────────────────────

def test_build_user_content_com_split_marker():
    prompt = f"contexto rico\n{la._SPLIT_MARKER}\nsolicitação"
    blocks = la._build_user_content(prompt)
    assert len(blocks) == 2
    assert blocks[0]["cache_control"]["type"] == "ephemeral"
    assert "contexto rico" in blocks[0]["text"]
    assert la._SPLIT_MARKER in blocks[1]["text"]


def test_build_user_content_sem_marker_so_query():
    blocks = la._build_user_content("apenas query")
    assert len(blocks) == 1
    assert blocks[0]["text"] == "apenas query"
    assert "cache_control" not in blocks[0]


# ── _status_header ───────────────────────────────────────────────────────────

def test_status_header_rag():
    h = la._status_header(True, 3, 0.85, False)
    assert "📚" in h
    assert "3 laudo" in h
    assert "0.85" in h


def test_status_header_fallback():
    h = la._status_header(False, 0, 0.0, False)
    assert "🧠" in h
    assert "Mem0" not in h


def test_status_header_com_memoria():
    h = la._status_header(True, 1, 0.9, True)
    assert "💾" in h
    assert "Mem0" in h


# ── _finalizar_laudo ─────────────────────────────────────────────────────────

def test_finalizar_laudo_aplica_filtros_e_assinatura():
    full = (
        "ACHADOS: normais.\n"
        "Status: ok\n"  # metadado a remover
        "[NOME DO MÉDICO]\n"
        "[CRM DO MÉDICO]\n"
        "[CAMPO PENDENTE]"
    )
    laudo, faltando = la._finalizar_laudo(full, {"medico": "Dr. A", "medico_crm": "1/SP"})
    assert "Status:" not in laudo
    assert "Dr. A" in laudo
    assert "1/SP" in laudo
    assert "CAMPO PENDENTE" in faltando


# ── _resolver_contexto_mem0 ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolver_contexto_mem0_sem_paciente():
    mem = MagicMock()
    mem.buscar_contexto_medico.return_value = "ctx-medico"
    ctx, hist, tem = await la._resolver_contexto_mem0(mem, "u1", "s", "rad", None)
    assert ctx == "ctx-medico"
    assert hist == ""
    assert tem is True


@pytest.mark.asyncio
async def test_resolver_contexto_mem0_com_paciente():
    mem = MagicMock()
    mem.buscar_contexto_medico.return_value = "ctx"
    mem.buscar_historico_paciente.return_value = "hist"
    ctx, hist, tem = await la._resolver_contexto_mem0(mem, "u", "s", "rad", "pac-1")
    assert hist == "hist"
    assert tem is True


@pytest.mark.asyncio
async def test_resolver_contexto_mem0_swallow_exception():
    mem = MagicMock()
    mem.buscar_contexto_medico.side_effect = ConnectionError("boom")
    mem.buscar_historico_paciente.side_effect = RuntimeError("boom")
    ctx, hist, tem = await la._resolver_contexto_mem0(mem, "u", "s", "rad", "pac")
    assert ctx == ""
    assert hist == ""
    assert tem is False


# ── _buscar_refs_rag ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_buscar_refs_rag_dedup_por_id():
    search = MagicMock()

    async def proprios(*a, **kw):
        return [{"id": "1", "score": 0.9}]

    async def gerais(*a, **kw):
        return [{"id": "1", "score": 0.7}, {"id": "2", "score": 0.6}]

    search.buscar_laudos_do_medico = proprios
    search.buscar_laudos_similares = gerais
    refs = await la._buscar_refs_rag(search, "u1", "s", "rad")
    ids = [r["id"] for r in refs]
    assert ids == ["1", "2"]  # "1" só aparece uma vez


# ── _persistir_mem0_bg ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_persistir_mem0_bg_dispara_task():
    mem = MagicMock()

    async def memo(**kw):
        return None

    mem.memorizar_interacao = memo
    la._persistir_mem0_bg(mem, "u", "s", "l", "rad", "rag", None)
    # cede loop pra task rodar
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_persistir_mem0_bg_loga_erro():
    mem = MagicMock()

    async def memo(**kw):
        raise RuntimeError("boom")

    mem.memorizar_interacao = memo
    la._persistir_mem0_bg(mem, "u", "s", "l", "rad", "rag", None)
    await asyncio.sleep(0)  # callback executa
