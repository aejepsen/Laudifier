"""Cobertura de LaudifierMemory — wrapper Mem0."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.services.memory_service import (
    LaudifierMemory,
    _formatar_memorias,
    _safe_results,
)


# ── _safe_results ────────────────────────────────────────────────────────────

def test_safe_results_lista_passa_through():
    assert _safe_results([{"a": 1}]) == [{"a": 1}]


def test_safe_results_dict_extrai_results():
    assert _safe_results({"results": [{"x": 1}]}) == [{"x": 1}]


def test_safe_results_dict_sem_results():
    assert _safe_results({"foo": "bar"}) == []


def test_safe_results_outros_tipos_devolve_vazio():
    assert _safe_results(None) == []
    assert _safe_results("string") == []
    assert _safe_results(42) == []


# ── _formatar_memorias ───────────────────────────────────────────────────────

def test_formatar_filtra_por_score():
    memorias = [
        {"memory": "alta confiança", "score": 0.9},
        {"memory": "baixa confiança", "score": 0.2},
    ]
    out = _formatar_memorias(memorias, [])
    assert "alta confiança" in out
    assert "baixa confiança" not in out


def test_formatar_inclui_secao_especialidade():
    medico = [{"memory": "prefere relatório curto", "score": 0.8}]
    esp = [{"memory": "padrão regional X", "score": 0.7}]
    out = _formatar_memorias(medico, esp)
    assert "PREFERÊNCIAS" in out
    assert "ESPECIALIDADE" in out
    assert "padrão regional X" in out


def test_formatar_vazio_retorna_string_vazia():
    assert _formatar_memorias([], []) == ""


def test_formatar_so_baixo_score_retorna_vazio():
    medico = [{"memory": "ruido", "score": 0.1}]
    assert _formatar_memorias(medico, []) == ""


# ── LaudifierMemory: lazy init ───────────────────────────────────────────────

def test_lazy_init_falha_silenciosa(monkeypatch):
    """get_memory raise → mem fica None, nada quebra."""
    from backend.services import memory_service

    def boom():
        raise ValueError("sem chave")

    monkeypatch.setattr(memory_service, "get_memory", boom)
    mem = LaudifierMemory()
    assert mem.mem is None
    assert mem._mem_initialized is True
    # Segunda leitura: não tenta de novo
    assert mem.mem is None


def test_lazy_init_sucesso_cacheia(monkeypatch):
    from backend.services import memory_service

    fake = MagicMock()
    monkeypatch.setattr(memory_service, "get_memory", lambda: fake)
    mem = LaudifierMemory()
    assert mem.mem is fake
    assert mem.mem is fake  # cacheado


# ── memorizar_interacao ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_memorizar_interacao_sem_mem_noop():
    mem = LaudifierMemory()
    mem._mem_initialized = True
    mem._mem = None
    # Não levanta
    await mem.memorizar_interacao("u1", "rx torax", "laudo", "radiologia", "rag")


@pytest.mark.asyncio
async def test_memorizar_interacao_chama_add():
    mem = LaudifierMemory()
    fake = MagicMock()
    mem._mem_initialized = True
    mem._mem = fake
    await mem.memorizar_interacao(
        medico_id="med-1",
        solicitacao="RX torax",
        laudo="ACHADOS: normal",
        especialidade="radiologia",
        tipo_geracao="rag",
        paciente_id="pac-1",
    )
    # 3 escopos: user, app, agent
    assert fake.add.call_count == 3


@pytest.mark.asyncio
async def test_memorizar_interacao_sem_paciente_nao_adiciona_agent():
    mem = LaudifierMemory()
    fake = MagicMock()
    mem._mem_initialized = True
    mem._mem = fake
    await mem.memorizar_interacao(
        medico_id="m1", solicitacao="s", laudo="l",
        especialidade="rad", tipo_geracao="rag",
    )
    assert fake.add.call_count == 2


@pytest.mark.asyncio
async def test_memorizar_interacao_swallow_exception():
    mem = LaudifierMemory()
    fake = MagicMock()
    fake.add.side_effect = ConnectionError("rede caiu")
    mem._mem_initialized = True
    mem._mem = fake
    # Não levanta
    await mem.memorizar_interacao("u1", "s", "l", "rad", "rag")


# ── memorizar_correcao ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_memorizar_correcao_sem_mem_noop():
    mem = LaudifierMemory()
    mem._mem_initialized = True
    mem._mem = None
    await mem.memorizar_correcao("u1", "antes", "depois", "rad")


@pytest.mark.asyncio
async def test_memorizar_correcao_chama_add():
    mem = LaudifierMemory()
    fake = MagicMock()
    mem._mem_initialized = True
    mem._mem = fake
    await mem.memorizar_correcao("m1", "ANTES", "DEPOIS", "radiologia")
    fake.add.assert_called_once()
    args, kwargs = fake.add.call_args
    assert kwargs["user_id"] == "m1"
    assert kwargs["metadata"]["tipo"] == "correcao"


@pytest.mark.asyncio
async def test_memorizar_correcao_swallow_exception():
    mem = LaudifierMemory()
    fake = MagicMock()
    fake.add.side_effect = TimeoutError("timeout")
    mem._mem_initialized = True
    mem._mem = fake
    await mem.memorizar_correcao("u", "a", "b", "rad")


# ── buscar_contexto_medico ───────────────────────────────────────────────────

def test_buscar_contexto_sem_mem_retorna_vazio():
    mem = LaudifierMemory()
    mem._mem_initialized = True
    mem._mem = None
    assert mem.buscar_contexto_medico("u1", "s", "rad") == ""


def test_buscar_contexto_formata_resultado():
    mem = LaudifierMemory()
    fake = MagicMock()
    fake.search.side_effect = [
        [{"memory": "padrão A", "score": 0.8}],
        [{"memory": "padrão esp", "score": 0.7}],
    ]
    mem._mem_initialized = True
    mem._mem = fake
    out = mem.buscar_contexto_medico("m1", "rx torax", "radiologia")
    assert "padrão A" in out
    assert fake.search.call_count == 2


def test_buscar_contexto_swallow_exception():
    mem = LaudifierMemory()
    fake = MagicMock()
    fake.search.side_effect = ConnectionError("boom")
    mem._mem_initialized = True
    mem._mem = fake
    assert mem.buscar_contexto_medico("u", "s", "rad") == ""


# ── buscar_historico_paciente ────────────────────────────────────────────────

def test_buscar_historico_sem_mem():
    mem = LaudifierMemory()
    mem._mem_initialized = True
    mem._mem = None
    assert mem.buscar_historico_paciente("p1", "s") == ""


def test_buscar_historico_filtra_por_score():
    mem = LaudifierMemory()
    fake = MagicMock()
    fake.search.return_value = [
        {"memory": "exame anterior X", "score": 0.7},
        {"memory": "ruido", "score": 0.2},
    ]
    mem._mem_initialized = True
    mem._mem = fake
    out = mem.buscar_historico_paciente("pac-1", "rx")
    assert "exame anterior X" in out
    assert "ruido" not in out
    assert "HISTÓRICO DO PACIENTE" in out


def test_buscar_historico_sem_resultados_retorna_vazio():
    mem = LaudifierMemory()
    fake = MagicMock()
    fake.search.return_value = []
    mem._mem_initialized = True
    mem._mem = fake
    assert mem.buscar_historico_paciente("p1", "s") == ""


def test_buscar_historico_swallow_exception():
    mem = LaudifierMemory()
    fake = MagicMock()
    fake.search.side_effect = RuntimeError("boom")
    mem._mem_initialized = True
    mem._mem = fake
    assert mem.buscar_historico_paciente("p", "s") == ""


# ── listar / deletar / limpar ────────────────────────────────────────────────

def test_listar_memorias_medico():
    mem = LaudifierMemory()
    fake = MagicMock()
    fake.get_all.return_value = [{"id": "1"}, {"id": "2"}]
    mem._mem_initialized = True
    mem._mem = fake
    assert len(mem.listar_memorias_medico("m1")) == 2


def test_listar_memorias_sem_mem():
    mem = LaudifierMemory()
    mem._mem_initialized = True
    mem._mem = None
    assert mem.listar_memorias_medico("m1") == []


def test_listar_memorias_swallow():
    mem = LaudifierMemory()
    fake = MagicMock()
    fake.get_all.side_effect = ConnectionError("x")
    mem._mem_initialized = True
    mem._mem = fake
    assert mem.listar_memorias_medico("m1") == []


def test_deletar_memoria():
    mem = LaudifierMemory()
    fake = MagicMock()
    mem._mem_initialized = True
    mem._mem = fake
    mem.deletar_memoria("mem-id-1")
    fake.delete.assert_called_once_with(memory_id="mem-id-1")


def test_deletar_memoria_sem_mem():
    mem = LaudifierMemory()
    mem._mem_initialized = True
    mem._mem = None
    mem.deletar_memoria("x")  # no-op


def test_deletar_memoria_swallow():
    mem = LaudifierMemory()
    fake = MagicMock()
    fake.delete.side_effect = ValueError("x")
    mem._mem_initialized = True
    mem._mem = fake
    mem.deletar_memoria("x")


def test_limpar_memorias_medico():
    mem = LaudifierMemory()
    fake = MagicMock()
    mem._mem_initialized = True
    mem._mem = fake
    mem.limpar_memorias_medico("m1")
    fake.delete_all.assert_called_once_with(user_id="m1")


def test_limpar_memorias_sem_mem():
    mem = LaudifierMemory()
    mem._mem_initialized = True
    mem._mem = None
    mem.limpar_memorias_medico("m1")


def test_limpar_memorias_swallow():
    mem = LaudifierMemory()
    fake = MagicMock()
    fake.delete_all.side_effect = OSError("x")
    mem._mem_initialized = True
    mem._mem = fake
    mem.limpar_memorias_medico("m1")


# ── get_memory ───────────────────────────────────────────────────────────────

def test_get_memory_sem_api_key(monkeypatch):
    from backend.services import memory_service
    monkeypatch.setenv("MEM0_API_KEY", "")
    memory_service.get_memory.cache_clear()
    with pytest.raises(ValueError, match="MEM0_API_KEY"):
        memory_service.get_memory()
    memory_service.get_memory.cache_clear()
