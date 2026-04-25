"""
Testes focados em matar mutantes que sobreviveram ao pytest baseline.

Estratégia: assertions de igualdade exata sobre strings/kwargs, em vez de
'contains'/'is not None', cobrindo cada literal e cada kwarg passado a
funções externas.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents import laudo_agent as la
from backend.agents import search_agent as sa


# ── _status_header — todos os literais e branches ────────────────────────────

def test_status_header_rag_exato():
    assert la._status_header(True, 3, 0.85, False) == (
        "📚 Usando 3 laudo(s) de referência (score: 0.85)\n\n"
    )


def test_status_header_rag_com_memoria_exato():
    assert la._status_header(True, 1, 0.99, True) == (
        "📚 Usando 1 laudo(s) de referência (score: 0.99)"
        "\n💾 Contexto personalizado do médico aplicado (Mem0)."
        "\n\n"
    )


def test_status_header_fallback_exato():
    assert la._status_header(False, 0, 0.0, False) == (
        "🧠 Gerando com base em conhecimento clínico geral — sem referência no repositório."
        "\n\n"
    )


def test_status_header_fallback_com_memoria_exato():
    assert la._status_header(False, 0, 0.0, True) == (
        "🧠 Gerando com base em conhecimento clínico geral — sem referência no repositório."
        "\n💾 Contexto personalizado do médico aplicado (Mem0)."
        "\n\n"
    )


def test_status_header_score_formato_2_decimais():
    # score 0.6 deve sair como 0.60
    out = la._status_header(True, 2, 0.6, False)
    assert "score: 0.60" in out


# ── _build_user_content — split exato ────────────────────────────────────────

def test_build_user_content_split_so_uma_vez():
    """split(_SPLIT_MARKER, 1) — múltiplos markers só dividem no primeiro."""
    marker = la._SPLIT_MARKER
    prompt = f"PRE\n\n{marker} A\n\n{marker} B"
    blocks = la._build_user_content(prompt)
    # ctx parte só deve ser "PRE", query inclui ambos markers
    assert blocks[0]["text"] == "PRE"
    assert blocks[1]["text"] == f"{marker} A\n\n{marker} B"


def test_build_user_content_ctx_rstrip_aplicado():
    marker = la._SPLIT_MARKER
    prompt = f"CTX   \n\n{marker} Q"
    blocks = la._build_user_content(prompt)
    # ctx deve ter rstrip
    assert blocks[0]["text"] == "CTX"
    assert not blocks[0]["text"].endswith(" ")


def test_build_user_content_ctx_block_tem_cache_control_ephemeral():
    marker = la._SPLIT_MARKER
    blocks = la._build_user_content(f"CTX\n\n{marker} Q")
    assert blocks[0] == {
        "type": "text",
        "text": "CTX",
        "cache_control": {"type": "ephemeral"},
    }
    assert blocks[1] == {"type": "text", "text": f"{marker} Q"}


def test_build_user_content_ctx_vazio_nao_entra_no_blocks():
    marker = la._SPLIT_MARKER
    blocks = la._build_user_content(f"   \n{marker} Q")
    # Só 1 bloco — query
    assert len(blocks) == 1
    assert blocks[0]["text"] == f"{marker} Q"


def test_build_user_content_sem_marker_unico_bloco_sem_cache():
    blocks = la._build_user_content("apenas pergunta")
    assert blocks == [{"type": "text", "text": "apenas pergunta"}]


# ── _formatar_refs — strings exatas ──────────────────────────────────────────

def test_formatar_refs_proprio_medico_exato():
    laudos = [{"source": "medico_aprovado", "score": 0.91, "content": "ABC"}]
    out = la._formatar_refs(laudos)
    assert out == "[Ref 1 — ⭐ LAUDO DO PRÓPRIO MÉDICO, score: 0.91]\nABC"


def test_formatar_refs_repositorio_exato():
    laudos = [
        {"especialidade": "rad", "tipo_laudo": "rx", "score": 0.5, "content": "X"},
    ]
    assert la._formatar_refs(laudos) == "[Ref 1 — rad/rx, score: 0.50]\nX"


def test_formatar_refs_separa_com_dupla_quebra():
    laudos = [
        {"score": 0.1, "content": "A", "especialidade": "e", "tipo_laudo": "t"},
        {"score": 0.2, "content": "B", "especialidade": "e", "tipo_laudo": "t"},
    ]
    out = la._formatar_refs(laudos)
    assert "\n\n" in out
    assert out.count("[Ref ") == 2
    assert out.startswith("[Ref 1")
    assert "[Ref 2" in out


def test_formatar_refs_trunca_content_em_1200():
    laudo = {"score": 0.5, "content": "X" * 2000, "especialidade": "e", "tipo_laudo": "t"}
    out = la._formatar_refs([laudo])
    # Deve ter exatamente 1200 X's no conteúdo após o cabeçalho
    assert out.count("X") == 1200


def test_formatar_refs_score_default_zero():
    laudos = [{"content": "X", "especialidade": "e", "tipo_laudo": "t"}]
    out = la._formatar_refs(laudos)
    assert "score: 0.00" in out


def test_formatar_refs_enumera_a_partir_de_1():
    laudos = [{"score": 0.1, "content": "A", "especialidade": "e", "tipo_laudo": "t"}]
    assert "[Ref 1 " in la._formatar_refs(laudos)


# ── _formatar_dados — branch sem dados ───────────────────────────────────────

def test_formatar_dados_falsy_dict_retorna_string_vazia():
    assert la._formatar_dados({}) == ""
    assert la._formatar_dados(None) == ""  # type: ignore[arg-type]


def test_formatar_dados_formato_indentado_exato():
    out = la._formatar_dados({"a": 1, "b": "x"})
    assert out == "  a: 1\n  b: x"


# ── _montar_prompt — assertions sobre cada cabeçalho/literal ────────────────

def test_montar_prompt_so_solicitacao_minimo():
    out = la._montar_prompt(
        solicitacao="rx torax",
        especialidade="radiologia",
        dados_clinicos={},
        contexto_mem0="",
        historico_paciente="",
        laudos_ref=[],
    )
    assert out == (
        "ESPECIALIDADE: RADIOLOGIA\n\n"
        "── SOLICITAÇÃO DO MÉDICO ──\nrx torax\n\n"
        "Gere o laudo médico completo. "
        "Aplique as preferências do médico quando disponíveis. "
        "Identifique e liste ao final quaisquer campos que precisam ser preenchidos."
    )


def test_montar_prompt_camada1_contexto_mem0_literal():
    out = la._montar_prompt(
        solicitacao="s", especialidade="rad", dados_clinicos={},
        contexto_mem0="PREF", historico_paciente="", laudos_ref=[],
    )
    assert "── CONTEXTO PERSONALIZADO DO MÉDICO (Mem0) ──\nPREF" in out


def test_montar_prompt_camada2_historico_literal():
    out = la._montar_prompt(
        solicitacao="s", especialidade="rad", dados_clinicos={},
        contexto_mem0="", historico_paciente="HIST", laudos_ref=[],
    )
    assert "── HISTÓRICO DO PACIENTE ──\nHIST" in out


def test_montar_prompt_camada3_dados_quando_truthy():
    out = la._montar_prompt(
        solicitacao="s", especialidade="rad",
        dados_clinicos={"k": "v"}, contexto_mem0="",
        historico_paciente="", laudos_ref=[],
    )
    assert "── DADOS DO EXAME E MÉDICO ──\n  k: v" in out


def test_montar_prompt_instrucao_so_nome():
    out = la._montar_prompt(
        solicitacao="s", especialidade="rad",
        dados_clinicos={"medico": "Dr X"}, contexto_mem0="",
        historico_paciente="", laudos_ref=[],
    )
    assert "IMPORTANTE: No laudo final, preencha automaticamente:\n" in out
    assert "  - [NOME DO MÉDICO] → Dr X\n" in out
    assert "[CRM DO MÉDICO]" not in out
    assert "  - [INDICAÇÃO CLÍNICA] → usar valor de 'indicacao' acima\n" in out
    assert "Apenas [ASSINATURA] deve permanecer como placeholder." in out


def test_montar_prompt_instrucao_so_crm():
    out = la._montar_prompt(
        solicitacao="s", especialidade="rad",
        dados_clinicos={"medico_crm": "12345"}, contexto_mem0="",
        historico_paciente="", laudos_ref=[],
    )
    assert "  - [CRM DO MÉDICO] → CRM 12345\n" in out
    assert "[NOME DO MÉDICO]" not in out


def test_montar_prompt_sem_medico_nao_emite_instrucao():
    out = la._montar_prompt(
        solicitacao="s", especialidade="rad",
        dados_clinicos={"outro": "x"}, contexto_mem0="",
        historico_paciente="", laudos_ref=[],
    )
    assert "IMPORTANTE: No laudo final" not in out


def test_montar_prompt_camada4_refs_so_quando_lista_truthy():
    laudos = [{"source": "medico_aprovado", "score": 0.9, "content": "C"}]
    out = la._montar_prompt(
        solicitacao="s", especialidade="rad", dados_clinicos={},
        contexto_mem0="", historico_paciente="", laudos_ref=laudos,
    )
    assert "── LAUDOS DE REFERÊNCIA DO REPOSITÓRIO ──\n[Ref 1 " in out


def test_montar_prompt_secoes_unidas_com_dupla_quebra():
    out = la._montar_prompt(
        solicitacao="s", especialidade="radiologia",
        dados_clinicos={"k": "v"}, contexto_mem0="",
        historico_paciente="", laudos_ref=[],
    )
    # Header de especialidade vem antes de uma quebra dupla
    assert out.startswith("ESPECIALIDADE: RADIOLOGIA\n\n")


def test_montar_prompt_solicitacao_apos_dupla_quebra():
    out = la._montar_prompt(
        solicitacao="QUERY", especialidade="x",
        dados_clinicos={}, contexto_mem0="",
        historico_paciente="", laudos_ref=[],
    )
    assert "── SOLICITAÇÃO DO MÉDICO ──\nQUERY\n\n" in out


# ── _preencher_assinatura — cobre cada branch e literal ─────────────────────

def test_preencher_assinatura_remove_bloco_assinatura_completo():
    laudo = "Conteúdo\n[ASSINATURA DO MÉDICO — algo]\nFim"
    out = la._preencher_assinatura(laudo, "", "")
    assert "[ASSINATURA" not in out
    assert "Conteúdo" in out
    assert "Fim" in out


def test_preencher_assinatura_substitui_nome_placeholder_exato():
    laudo = "[NOME DO MÉDICO]"
    out = la._preencher_assinatura(laudo, "Dr Y", "")
    assert out == "Dr Y"


def test_preencher_assinatura_substitui_crm_placeholder_exato():
    laudo = "[CRM DO MÉDICO]"
    out = la._preencher_assinatura(laudo, "", "999")
    assert out == "999"


def test_preencher_assinatura_preenche_linha_crm_vazia():
    out = la._preencher_assinatura("CRM:", "", "888")
    assert out == "CRM: 888"


def test_preencher_assinatura_insere_nome_apos_underscores():
    laudo = "______________"
    out = la._preencher_assinatura(laudo, "Dr Z", "777")
    assert out == "______________\nDr Z\nCRM: 777"


def test_preencher_assinatura_so_nome_apos_underscores_sem_crm():
    out = la._preencher_assinatura("____________", "Dr W", "")
    assert out == "____________\nDr W"


def test_preencher_assinatura_nao_duplica_se_nome_ja_presente():
    laudo = "______________\nDr Já\nFim"
    out = la._preencher_assinatura(laudo, "Dr Já", "")
    # Não insere de novo
    assert out.count("Dr Já") == 1


def test_preencher_assinatura_pula_linhas_vazias_e_compara_nome():
    laudo = "______________\n\n\nDr Já"
    out = la._preencher_assinatura(laudo, "Dr Já", "")
    assert out.count("Dr Já") == 1


def test_preencher_assinatura_collapsa_3_quebras_em_2():
    out = la._preencher_assinatura("a\n\n\n\nb", "", "")
    assert out == "a\n\nb"


def test_preencher_assinatura_rstrip_final():
    out = la._preencher_assinatura("texto   \n  \n", "", "")
    assert out == "texto"


# ── _finalizar_laudo — defaults dos .get() ──────────────────────────────────

def test_finalizar_laudo_defaults_string_vazia():
    """Sem 'medico' nem 'medico_crm' nos dados — defaults devem ser '' (não outro literal)."""
    laudo, campos = la._finalizar_laudo("texto", {})
    # Se default fosse "XXXX", apareceria no laudo
    assert "XXXX" not in laudo


def test_finalizar_laudo_aplica_assinatura_e_extrai_campos():
    laudo, campos = la._finalizar_laudo(
        "[NOME DO MÉDICO] [CRM DO MÉDICO]\n[OUTRO]",
        {"medico": "Dr A", "medico_crm": "111"},
    )
    assert "Dr A" in laudo
    assert "111" in laudo
    assert "OUTRO" in campos


# ── _persistir_mem0_bg — captura kwargs ──────────────────────────────────────

@pytest.mark.asyncio
async def test_persistir_mem0_bg_passa_todos_kwargs_corretos():
    mem = MagicMock()
    captured = {}

    async def _fake(**kwargs):
        captured.update(kwargs)
        return None

    mem.memorizar_interacao = _fake
    la._persistir_mem0_bg(
        mem, user_id="med-1", solicitacao="rx", laudo="L",
        especialidade="rad", tipo_geracao="rag", paciente_id="pac-7",
    )
    # Aguarda task agendada
    import asyncio
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert captured == {
        "medico_id": "med-1",
        "solicitacao": "rx",
        "laudo": "L",
        "especialidade": "rad",
        "tipo_geracao": "rag",
        "paciente_id": "pac-7",
    }


@pytest.mark.asyncio
async def test_persistir_mem0_bg_paciente_id_none_passa_none():
    mem = MagicMock()
    captured = {}

    async def _fake(**kwargs):
        captured.update(kwargs)

    mem.memorizar_interacao = _fake
    la._persistir_mem0_bg(
        mem, "u", "s", "l", "e", "t", None,
    )
    import asyncio
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert captured["paciente_id"] is None


@pytest.mark.asyncio
async def test_persistir_mem0_bg_callback_loga_excecao(caplog):
    mem = MagicMock()

    async def _boom(**_):
        raise RuntimeError("kaboom")

    mem.memorizar_interacao = _boom
    import logging
    with caplog.at_level(logging.WARNING, logger="backend.agents.laudo_agent"):
        la._persistir_mem0_bg(mem, "u", "s", "l", "e", "t", None)
        import asyncio
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    assert any("memorizar_interacao falhou" in rec.message for rec in caplog.records)


# ── search_agent._get_qdrant_client — kwargs exatos ─────────────────────────

def test_get_qdrant_client_passa_kwargs_corretos():
    sa._qdrant_client = None
    with patch.object(sa, "AsyncQdrantClient") as mock_q:
        mock_q.return_value = MagicMock()
        sa._get_qdrant_client()
        args, kwargs = mock_q.call_args
        assert kwargs == {
            "url": sa.QDRANT_URL,
            "api_key": sa.QDRANT_KEY or None,
            "timeout": 30,
            "check_compatibility": False,
        }
    sa._qdrant_client = None


def test_get_qdrant_client_singleton_so_constroi_uma_vez():
    sa._qdrant_client = None
    with patch.object(sa, "AsyncQdrantClient") as mock_q:
        mock_q.return_value = MagicMock()
        sa._get_qdrant_client()
        sa._get_qdrant_client()
        sa._get_qdrant_client()
        assert mock_q.call_count == 1
    sa._qdrant_client = None


def test_get_model_passa_modelo_correto():
    sa._model = None
    sa._model_error = None
    with patch.object(sa, "SentenceTransformer") as mock_st:
        mock_st.return_value = MagicMock()
        sa._get_model()
        args, kwargs = mock_st.call_args
        assert args[0] == sa.EMB_MODEL
    sa._model = None


# ── search_agent.LaudoSearchAgent — _embed prefixo E5 EXATO ─────────────────

@pytest.mark.asyncio
async def test_embed_prefix_query_exato():
    import numpy as np
    agent = sa.LaudoSearchAgent.__new__(sa.LaudoSearchAgent)
    fake = MagicMock()
    fake.encode.return_value = np.array([0.0])
    with patch.object(sa, "_get_model", return_value=fake):
        await agent._embed("HELLO")
    args, kwargs = fake.encode.call_args
    assert args[0] == "query: HELLO"
    # normalize_embeddings deve ser True
    assert kwargs.get("normalize_embeddings") is True


# ── _normalizar_instrucao_linhas / _extrair / _substituir — exato ───────────

def test_normalizar_instrucao_so_numero_no_inicio_converte():
    assert la._normalizar_instrucao_linhas("16 frontal") == "linha 16: frontal"


def test_normalizar_instrucao_sem_numero_inalterado():
    s = "sem numero"
    assert la._normalizar_instrucao_linhas(s) == s


def test_substituir_linha_texto_indices_1based():
    laudo = "L1\nL2\nL3"
    out = la._substituir_linha_texto(laudo, 2, "NOVA")
    assert out == "L1\nNOVA\nL3"


def test_extrair_linha_referenciada_retorna_tupla_com_texto_da_linha():
    laudo = "A\nB\nC"
    out = la._extrair_linha_referenciada(laudo, "linha 2: faça X")
    assert out == (2, "B", "faça X")
