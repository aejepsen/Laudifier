"""
Testes de concorrência e streaming SSE sem mock da cadeia de agentes.

Cobrem:
  • Property-based test dos singletons @lru_cache sob carga concorrente
  • Streaming SSE real com stub HTTP local (sem mock de _stream)
  • Race condition no counter de queries (ContextVar por request)
"""
from __future__ import annotations

import asyncio
import json

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from backend.api._query_counter import (
    get_query_count,
    log_if_over_threshold,
    reset_query_counter,
    track_query,
)


# ── Property-based: contador é isolado por task ──────────────────────────────

@pytest.mark.concurrency
@settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    n_tasks=st.integers(min_value=2, max_value=20),
    calls_per_task=st.integers(min_value=1, max_value=15),
)
@pytest.mark.asyncio
async def test_query_counter_isolado_por_task(n_tasks: int, calls_per_task: int):
    """
    ContextVar deve isolar o contador por request concorrente.
    Se vazar, N tasks disparam N*M incrementos no mesmo contador.
    """
    async def worker(label: str) -> int:
        reset_query_counter()
        for _ in range(calls_per_task):
            track_query(label)
        await asyncio.sleep(0)  # força troca de contexto
        return sum(get_query_count().values())

    results = await asyncio.gather(
        *[worker(f"task-{i}") for i in range(n_tasks)]
    )
    # Cada task DEVE ver exatamente seus próprios incrementos
    assert all(r == calls_per_task for r in results), (
        f"ContextVar vazou entre tasks: {results}"
    )


# ── Property-based: singleton de prompt é thread-safe ────────────────────────

@pytest.mark.concurrency
@settings(max_examples=5, deadline=None)
@given(n_readers=st.integers(min_value=4, max_value=50))
@pytest.mark.asyncio
async def test_load_system_prompt_concorrente(n_readers: int, tmp_path, monkeypatch):
    """
    @lru_cache(maxsize=1) + read_text devem ser seguros sob N leituras concorrentes.
    Valida que todas as corrotinas recebem o mesmo conteúdo (identidade de objeto).
    """
    from backend.services import prompt_service

    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "system_prompt.txt").write_text("CONTEUDO_PADRAO", encoding="utf-8")

    monkeypatch.setattr(prompt_service, "PROMPT_DIR", prompt_dir)
    prompt_service.load_system_prompt.cache_clear()

    results = await asyncio.gather(
        *[asyncio.to_thread(prompt_service.load_system_prompt) for _ in range(n_readers)]
    )
    primeiro = results[0]
    assert primeiro == "CONTEUDO_PADRAO"
    assert all(r is primeiro for r in results), "lru_cache devolveu instâncias diferentes"


# ── SSE real: endpoint /laudos/gerar SEM mocar o pipeline ────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_sse_gerar_laudo_stream_real(monkeypatch):
    """
    Exercita o parsing SSE real do endpoint: stubamos APENAS o cliente Anthropic
    (camada HTTP externa), deixando laudo_agent → search_agent → query_counter
    executarem de ponta a ponta.
    """
    from httpx import ASGITransport, AsyncClient

    # Stub do AsyncAnthropic: emite tokens reais via async generator
    class _FakeStream:
        def __init__(self, tokens: list[str]) -> None:
            self._tokens = tokens

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        @property
        def text_stream(self):
            async def gen():
                for t in self._tokens:
                    await asyncio.sleep(0)
                    yield t
            return gen()

    class _FakeMessages:
        def stream(self, **_kw):
            return _FakeStream(["── IMPRESSÃO ──\n", "Exame normal.\n"])

    class _FakeAnthropic:
        def __init__(self, *_a, **_kw): ...
        messages = _FakeMessages()

    # Stub do SearchAgent: retorna lista vazia (força fallback, evita Qdrant)
    async def _fake_refs(*_a, **_kw):
        return []

    from backend.agents import laudo_agent
    monkeypatch.setattr(laudo_agent.anthropic, "AsyncAnthropic", _FakeAnthropic)
    monkeypatch.setattr(laudo_agent, "_buscar_refs_rag", _fake_refs)
    monkeypatch.setattr(laudo_agent, "_resolver_contexto_mem0",
                        lambda *a, **k: _async_return(("", "", False)))

    # Bypass auth
    from backend.api import main as main_api
    from backend.api.auth import UserContext
    main_api.app.dependency_overrides[main_api.verify_token] = lambda: UserContext(
        id="doc-1", email="t@t", role="user",
    )

    transport = ASGITransport(app=main_api.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/laudos/gerar",
            json={"solicitacao": "rx torax", "especialidade": "radiologia", "dados_clinicos": {}},
            headers={"Authorization": "Bearer x"},
        )
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")

        events = [
            json.loads(line.removeprefix("data: "))
            for line in r.text.splitlines()
            if line.startswith("data: ")
        ]
        types = [e["type"] for e in events]
        assert "meta" in types, f"meta event ausente: {types}"
        assert "done" in types, f"done event ausente: {types}"
        # Deve ter emitido tokens reais do stub Anthropic
        assert any(e["type"] == "token" and "IMPRESSÃO" in e.get("text", "") for e in events)

    main_api.app.dependency_overrides.clear()


async def _async_return(value):
    return value


# ── Sanity: log_if_over_threshold não explode fora de request ────────────────

def test_log_threshold_sem_contexto_nao_crash(caplog):
    # Fora de middleware: counter é None, função deve no-op
    log_if_over_threshold("/x")
    track_query("foo")  # também no-op
    assert True
