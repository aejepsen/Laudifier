# /hm-engineer — Auditoria Laudifier

Data: 2026-04-24 · Escopo: backend + laudifier/backend + scripts raiz

---

## CRITICOS (bloqueiam shippar)

### C1. Árvore duplicada: `./backend/` ≡ `./laudifier/backend/`
Onde: raiz do repo
Problema: 16k+ LOC duplicadas. MI idêntico, CC idêntico (`gerar_laudo_stream` CC=17 nos dois). Commits em um lado não chegam no outro.
Impacto: drift silencioso, fixes aplicados metade, auditoria retorna findings duplicados, CI ambígua.
Fix: decidir a fonte canônica (provavelmente `./laudifier/backend/`), deletar a outra, atualizar `Dockerfile`/`docker-compose.yml`/imports. Uma única árvore.

### C2. `.env` commitado
Onde: `./laudifier/backend/.env`
Problema: arquivo presente no working tree, sem `.env.example`.
Impacto: secrets (SUPABASE, ANTHROPIC, QDRANT, MEM0) vazam em clone/fork. `git log -- **/.env` provavelmente expõe histórico.
Fix: `git rm --cached` em todos os `.env`, rotacionar todas as chaves, commitar `.env.example` com placeholders, garantir `.env` no `.gitignore` e `.dockerignore`.

### C3. Cobertura de teste real desconhecida e provavelmente < 20%
Onde: `backend/tests/test_api.py` (386 LOC, 30 tests, 46 asserts) + `test_laudo.py` (236 LOC, 14 tests, 25 asserts)
Problema: 44 testes cobrindo ~3.500 LOC de produção. Sem `.coveragerc`, sem configuração `[tool.coverage]`, sem `htmlcov/` ou `coverage.xml`. Nunca foi medida.
Impacto: impossível afirmar world-class. Linhas críticas de `laudo_agent.gerar_laudo_stream` (CC=17) sem garantia de execução.
Fix: adicionar `pytest-cov`, definir `fail_under=80` em `pyproject.toml`, rodar `pytest --cov=backend --cov-branch --cov-report=term-missing` e tapar buracos.

### C4. Falso positivo de cobertura (mocking agressivo)
Onde: `backend/tests/test_api.py:253,273,287` — `async def _fake_stream`, `_stream` substituem o pipeline real
Problema: os testes que dão a impressão de cobrir `/gerar-laudo` (streaming SSE) trocam toda a cadeia `laudo_agent → search_agent → qdrant → anthropic` por stub. A linha executa, a lógica nunca é exercitada.
Impacto: bug em parsing de stream, ordering de `asyncio.gather`, timeout de `asyncio.wait_for` — nenhum é pego. Coverage reporta linha verde, mutation score seria baixíssimo.
Fix: adicionar testes de integração com httpx + servidor stub local (responde SSE real), rodar `mutmut run --paths-to-mutate=backend/agents/` — alvo: mutation score ≥ 70% nos agentes.

### C5. N+1 em indexação (serial network I/O)
Onde: `backend/agents/search_agent.py:186` e `:225` — `for i, chunk in enumerate(chunks): vec = await asyncio.to_thread(embed, chunk)`
Problema: cada chunk embed serialmente. 40 chunks = 40 RTTs sequenciais antes do `qdrant.upsert`.
Impacto: latência linear no nº de chunks. Em laudos longos, endpoint de indexação trava worker por segundos.
Fix: `vecs = await asyncio.gather(*[asyncio.to_thread(embed, c) for c in chunks])` ou batchar no encoder (`model.encode(chunks, batch_size=32)`).

---

## ALTOS

### A1. Complexidade ciclomática fora do padrão senior
- `laudo_agent.gerar_laudo_stream` CC=17 (SonarQube C) — 1 função, 406 SLOC no arquivo
- `laudo_agent._preencher_assinatura` CC=12 (C)
Fix: extrair `_resolver_contexto_mem0`, `_montar_user_content`, `_stream_tokens`, `_persistir_resultado`. Alvo: CC ≤ 10 (B) por função.

### A2. `except Exception` genérico em fluxo crítico (~22 ocorrências)
Onde: `memory_service.py` (8 ocorrências em 278 LOC), `main.py:82,203,242,332,372,478,512`, `search_agent.py:52,76,105,165,206,244`
Problema: engole `asyncio.CancelledError`, `httpx.ConnectError`, `anthropic.APIError` no mesmo balde. Silencia erros de auth/rate-limit.
Fix: especificar (`httpx.HTTPError`, `anthropic.APIError`, `QdrantException`). Nunca capturar `Exception` exceto em boundary de request e com re-raise estruturado.

### A3. Middleware de N+1 ausente
Onde: `backend/api/main.py`
Problema: sem contador de queries por request. Não há threshold, não há alerta.
Fix: middleware que injeta counter em `request.state`, instrumenta `qdrant.query_points`, `supabase.*`, `mem0.*` via wrapper, loga warning quando > 10 calls/request.

### A4. Singleton `@lru_cache(maxsize=1)` em clients sem teste de concorrência
Onde: `services/laudo_service.py:201`, `prompt_service.py:7`, `memory_service.py:23`
Problema: instâncias únicas compartilhadas entre requests. Se a lib (mem0) muta estado interno (histórico), corrida entre 2 requests simultâneos.
Fix: property-based test com `hypothesis` + `pytest-asyncio` disparando N corrotinas concorrentes chamando `memory_service.add()` e validando isolamento por `user_id`. Adicionar `asyncio.Lock()` se mem0 não for thread-safe.

### A5. `main.py` com 592-614 LOC — módulo-deus
Fix: separar em `routes/laudos.py`, `routes/dashboard.py`, `routes/auth.py`, `middleware/`. Alvo: ≤ 200 LOC por módulo HTTP.

---

## MEDIOS

- **M1.** Sem `mutmut`, `hypothesis`, `py-spy` instalados. Adicionar a `requirements-dev.txt` e rodar em CI.
- **M2.** Sem profiler em runtime: integrar `py-spy record -o profile.svg --pid <pid>` no docker-compose de perf, `pprof`-like via `pyinstrument` em endpoint `/debug/profile` (gated por auth admin).
- **M3.** `processor.py` 552 LOC, script monolítico — dividir em `extract/`, `transform/`, `load/`.
- **M4.** `pytest.ini` existe em `backend/` mas sem `addopts = --strict-markers --strict-config -ra --cov-branch`.
- **M5.** Streaming SSE (`gerar_laudo_stream`) sem teste de desconexão de cliente — memory leak potencial se generator não for fechado.

---

## METRICAS

| Métrica | Valor | Alvo world-class |
|---|---|---|
| CC média (backend) | C (14.5) | ≤ B (10) |
| MI mínimo | 33 (test_api.py) | ≥ 65 prod, ≥ 40 test |
| Módulo maior | main.py 614 LOC | ≤ 300 |
| Testes | 44 | ≥ 200 (ratio 1:15 SLOC) |
| Mutation score | não medido | ≥ 70% |
| Cobertura branch | não medido | ≥ 80% |
| `except Exception` | 22 ocorrências | 0 em lib, < 3 em boundary |

---

## RECOMENDACAO

**Não shippe.** 3 criticos bloqueiam: árvore duplicada (C1), `.env` commitado (C2), cobertura inexistente + falso positivo de stream (C3/C4). C5 é performance bloqueante em indexação.

Ordem de execução:
1. Rotacionar secrets + remover `.env` do git + decidir árvore canônica
2. Instrumentar cobertura + mutmut + hypothesis na CI
3. Refatorar `gerar_laudo_stream` (CC 17 → ≤ 10) e corrigir N+1 do search_agent
4. Middleware de query-count + profiler gated
5. Property-based tests de concorrência nos singletons
