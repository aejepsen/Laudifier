"""Cobertura de LaudoSearchAgent — Qdrant + embeddings."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from backend.agents import search_agent as sa


# ── _build_filter ────────────────────────────────────────────────────────────

def test_build_filter_vazio():
    agent = sa.LaudoSearchAgent.__new__(sa.LaudoSearchAgent)
    assert agent._build_filter("", "") is None


def test_build_filter_so_especialidade():
    agent = sa.LaudoSearchAgent.__new__(sa.LaudoSearchAgent)
    f = agent._build_filter("Radiologia", "")
    assert f is not None
    assert len(f.must) == 1


def test_build_filter_ambos():
    agent = sa.LaudoSearchAgent.__new__(sa.LaudoSearchAgent)
    f = agent._build_filter("Radiologia", "RX_TORAX")
    assert len(f.must) == 2


def test_build_filter_lowercase_normaliza():
    agent = sa.LaudoSearchAgent.__new__(sa.LaudoSearchAgent)
    f = agent._build_filter("RADIOLOGIA", "")
    assert f.must[0].match.value == "radiologia"


# ── _chunk_text ──────────────────────────────────────────────────────────────

def test_chunk_text_curto():
    chunks = sa.LaudoSearchAgent._chunk_text("texto curto", size=600)
    assert len(chunks) == 1


def test_chunk_text_longo_quebra():
    palavras = "palavra " * 200  # ~1600 chars
    chunks = sa.LaudoSearchAgent._chunk_text(palavras, size=600, overlap=5)
    assert len(chunks) > 1


def test_chunk_text_overlap_preserva_palavras():
    palavras = "p1 " * 300
    chunks = sa.LaudoSearchAgent._chunk_text(palavras, size=600, overlap=10)
    # Cada chunk deve começar com palavras válidas
    assert all(c.startswith("p1") for c in chunks)


# ── _to_dict ─────────────────────────────────────────────────────────────────

def test_to_dict_extrai_payload():
    agent = sa.LaudoSearchAgent.__new__(sa.LaudoSearchAgent)
    point = SimpleNamespace(
        id="abc-123",
        score=0.87,
        payload={
            "content": "texto",
            "source_name": "fonte.pdf",
            "especialidade": "rad",
            "tipo_laudo": "rx",
        },
    )
    out = agent._to_dict(point)
    assert out["id"] == "abc-123"
    assert out["score"] == 0.87
    assert out["content"] == "texto"


def test_to_dict_payload_none():
    agent = sa.LaudoSearchAgent.__new__(sa.LaudoSearchAgent)
    point = SimpleNamespace(id="x", score=0.5, payload=None)
    out = agent._to_dict(point)
    assert out["content"] == ""


# ── _get_model singleton ─────────────────────────────────────────────────────

def test_get_model_cacheia_falha():
    sa._model = None
    sa._model_error = None
    with patch.object(sa, "SentenceTransformer", side_effect=RuntimeError("download falhou")):
        with pytest.raises(RuntimeError):
            sa._get_model()
        # Segunda chamada deve repropagar o mesmo erro sem reinstanciar
        with pytest.raises(RuntimeError):
            sa._get_model()
    sa._model_error = None


def test_get_model_cacheia_sucesso():
    sa._model = None
    sa._model_error = None
    fake_model = MagicMock()
    with patch.object(sa, "SentenceTransformer", return_value=fake_model):
        m1 = sa._get_model()
        m2 = sa._get_model()
        assert m1 is m2 is fake_model
    sa._model = None


# ── _get_qdrant_client singleton ─────────────────────────────────────────────

def test_get_qdrant_client_singleton():
    sa._qdrant_client = None
    with patch.object(sa, "AsyncQdrantClient") as mock_q:
        mock_q.return_value = MagicMock()
        c1 = sa._get_qdrant_client()
        c2 = sa._get_qdrant_client()
        assert c1 is c2
        mock_q.assert_called_once()
    sa._qdrant_client = None


# ── _embed ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_embed_aplica_prefixo_e5():
    agent = sa.LaudoSearchAgent.__new__(sa.LaudoSearchAgent)
    fake_model = MagicMock()
    fake_model.encode.return_value = np.array([0.1, 0.2, 0.3])
    with patch.object(sa, "_get_model", return_value=fake_model):
        vec = await agent._embed("rx torax")
    assert vec == [0.1, 0.2, 0.3]
    args, kwargs = fake_model.encode.call_args
    assert args[0] == "query: rx torax"


# ── buscar_laudos_similares ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_buscar_similares_embedding_falha_retorna_vazio():
    agent = sa.LaudoSearchAgent.__new__(sa.LaudoSearchAgent)
    agent.qdrant = MagicMock()
    with patch.object(agent, "_embed", new=AsyncMock(side_effect=RuntimeError("embed off"))):
        out = await agent.buscar_laudos_similares("q", "rad")
    assert out == []


@pytest.mark.asyncio
async def test_buscar_similares_qdrant_falha_retorna_vazio():
    agent = sa.LaudoSearchAgent.__new__(sa.LaudoSearchAgent)
    agent.qdrant = MagicMock()
    agent.qdrant.query_points = AsyncMock(side_effect=ConnectionError("down"))
    with patch.object(agent, "_embed", new=AsyncMock(return_value=[0.1] * 1024)):
        out = await agent.buscar_laudos_similares("q", "rad")
    assert out == []


@pytest.mark.asyncio
async def test_buscar_similares_fallback_sem_filtro():
    """Filtrada vazia → retry sem filtro."""
    agent = sa.LaudoSearchAgent.__new__(sa.LaudoSearchAgent)
    agent.qdrant = MagicMock()

    point = SimpleNamespace(id="x", score=0.7, payload={"content": "txt"})
    # 1ª chamada: vazio ; 2ª (sem filtro): retorna point
    agent.qdrant.query_points = AsyncMock(side_effect=[
        SimpleNamespace(points=[]),
        SimpleNamespace(points=[point]),
    ])
    with patch.object(agent, "_embed", new=AsyncMock(return_value=[0.1] * 1024)):
        out = await agent.buscar_laudos_similares("q", "rad")
    assert len(out) == 1
    assert agent.qdrant.query_points.call_count == 2


@pytest.mark.asyncio
async def test_buscar_similares_resultados_diretos():
    agent = sa.LaudoSearchAgent.__new__(sa.LaudoSearchAgent)
    agent.qdrant = MagicMock()
    point = SimpleNamespace(id="x", score=0.8, payload={"content": "ok"})
    agent.qdrant.query_points = AsyncMock(return_value=SimpleNamespace(points=[point]))
    with patch.object(agent, "_embed", new=AsyncMock(return_value=[0.1] * 1024)):
        out = await agent.buscar_laudos_similares("q", "rad")
    assert len(out) == 1
    # sem filtro adicional
    assert agent.qdrant.query_points.call_count == 1


# ── buscar_laudos_do_medico ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_buscar_do_medico_embedding_falha():
    agent = sa.LaudoSearchAgent.__new__(sa.LaudoSearchAgent)
    agent.qdrant = MagicMock()
    with patch.object(agent, "_embed", new=AsyncMock(side_effect=ValueError("x"))):
        out = await agent.buscar_laudos_do_medico("med-1", "q")
    assert out == []


@pytest.mark.asyncio
async def test_buscar_do_medico_qdrant_falha():
    agent = sa.LaudoSearchAgent.__new__(sa.LaudoSearchAgent)
    agent.qdrant = MagicMock()
    agent.qdrant.query_points = AsyncMock(side_effect=RuntimeError("x"))
    with patch.object(agent, "_embed", new=AsyncMock(return_value=[0.1] * 1024)):
        out = await agent.buscar_laudos_do_medico("med-1", "q", "rad")
    assert out == []


@pytest.mark.asyncio
async def test_buscar_do_medico_sucesso_com_especialidade():
    agent = sa.LaudoSearchAgent.__new__(sa.LaudoSearchAgent)
    agent.qdrant = MagicMock()
    point = SimpleNamespace(id="m1", score=0.7, payload={"content": "x"})
    agent.qdrant.query_points = AsyncMock(return_value=SimpleNamespace(points=[point]))
    with patch.object(agent, "_embed", new=AsyncMock(return_value=[0.1] * 1024)):
        out = await agent.buscar_laudos_do_medico("med-1", "q", "Radiologia", top=2)
    assert len(out) == 1
    # Filtro deve ter 2 conditions (medico_id + especialidade)
    args, kwargs = agent.qdrant.query_points.call_args
    assert len(kwargs["query_filter"].must) == 2


# ── indexar_laudo_aprovado ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_indexar_laudo_aprovado_chama_upsert():
    agent = sa.LaudoSearchAgent.__new__(sa.LaudoSearchAgent)
    agent.qdrant = MagicMock()
    agent.qdrant.upsert = AsyncMock()
    fake_model = MagicMock()
    fake_model.encode.return_value = np.array([[0.1] * 1024, [0.2] * 1024])
    with patch.object(sa, "_get_model", return_value=fake_model):
        await agent.indexar_laudo_aprovado(
            laudo_id="l-1", medico_id="m-1",
            laudo_text="palavra " * 200,  # gera múltiplos chunks
            especialidade="Radiologia", solicitacao="rx",
        )
    agent.qdrant.upsert.assert_called_once()
    args, kwargs = agent.qdrant.upsert.call_args
    assert len(kwargs["points"]) >= 1


@pytest.mark.asyncio
async def test_indexar_laudo_aprovado_swallow_exception():
    agent = sa.LaudoSearchAgent.__new__(sa.LaudoSearchAgent)
    agent.qdrant = MagicMock()
    with patch.object(sa, "_get_model", side_effect=RuntimeError("modelo morto")):
        # Não deve levantar
        await agent.indexar_laudo_aprovado("l", "m", "t", "rad", "rx")


# ── indexar_no_repositorio_geral ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_indexar_repositorio_geral():
    agent = sa.LaudoSearchAgent.__new__(sa.LaudoSearchAgent)
    agent.qdrant = MagicMock()
    agent.qdrant.upsert = AsyncMock()
    fake_model = MagicMock()
    fake_model.encode.return_value = np.array([[0.1] * 1024])
    with patch.object(sa, "_get_model", return_value=fake_model):
        await agent.indexar_no_repositorio_geral("l-1", "texto curto", "rad", "rx")
    agent.qdrant.upsert.assert_called_once()


@pytest.mark.asyncio
async def test_indexar_repositorio_geral_swallow():
    agent = sa.LaudoSearchAgent.__new__(sa.LaudoSearchAgent)
    agent.qdrant = MagicMock()
    with patch.object(sa, "_get_model", side_effect=ValueError("x")):
        await agent.indexar_no_repositorio_geral("l", "t", "rad", "rx")
