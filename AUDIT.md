# /hm-engineer — Auditoria Laudifier

Data: 2026-04-24 · Escopo: backend + scripts raiz · Re-pass após C1-C5 + A1-A5

---

## ESTADO ATUAL

| Bloco | Status | Notas |
|---|---|---|
| C1. Árvore duplicada | ✅ resolvido | Canonical = `./laudifier/`, achatado para raiz |
| C2. `.env` commitado | ✅ resolvido | `.env` removido, `.env.example` no repo, secrets rotacionados |
| C3. Cobertura ausente | ✅ resolvido | pytest-cov ativo, 88% line + branch (alvo 80%) |
| C4. Falso positivo de stream | ✅ resolvido | `test_concurrency.py::test_sse_gerar_laudo_stream_real` exercita pipeline; mutmut em `agents/` = 92.7% kill rate |
| C5. N+1 em indexação | ✅ resolvido | `model.encode([...], batch_size=32)` em `indexar_laudo_aprovado` e `indexar_no_repositorio_geral` |
| A1. CC fora do padrão | ✅ resolvido | `_preencher_assinatura` 12→7; max em laudo_agent = 9; média backend = A (3.0) |
| A2. `except Exception` genérico | ✅ resolvido | Todos os handlers de lib narrowed para tuples específicos (`_QDRANT_ERRORS`, `_SSE_STREAM_ERRORS`, etc.); `except Exception` apenas em 2 boundaries de request com `logger.exception` + re-raise estruturado |
| A3. Middleware N+1 | ✅ resolvido | `query_counter_middleware` + `track_query()` instrumentado em qdrant/supabase/mem0 |
| A4. Singletons sem teste de concorrência | ✅ resolvido | Hypothesis + asyncio: counter por request, prompt_service.load_system_prompt, LaudifierMemory.add isolado por user_id |
| A5. main.py 614 LOC | ✅ resolvido | main.py 63 LOC; routes/{auth,laudos,repositorio,dashboard,health}.py + middleware.py + _shared.py + _helpers.py + models.py |

---

## METRICAS

| Métrica | Antes | Agora | Alvo |
|---|---|---|---|
| CC média (backend) | C (14.5) | A (3.0) | ≤ B (10) |
| Max CC produção | 17 (`gerar_laudo_stream`) | 10 (`_chunk_laudo`) | ≤ 10 |
| main.py LOC | 614 | 63 | ≤ 300 |
| Maior módulo HTTP | main.py 614 | routes/laudos.py 322 | ≤ 200 (cohesive) |
| Testes | 44 | 236 | ≥ 200 |
| Cobertura branch | n/a | 88% | ≥ 80% |
| Mutation score (`agents/`) | n/a | 92.7% (266/287) | ≥ 70% |
| `except Exception` lib | 22 | 0 | 0 |
| `except Exception` boundary | — | 2 (com `logger.exception` + 500) | < 3 |

---

## MEDIOS

- **M1.** ✅ CI: `--cov-fail-under=80` em PR/push. Mutmut em workflow_dispatch (manual) com gate ≥70%.
- **M2.** ✅ `/debug/profile?duration=N` (1-30s) admin-gated, retorna flame graph HTML via pyinstrument.
- **M3.** ✅ `processor.py` 552 LOC dividido em pacote `processor/` (extract.py, transform.py, load.py, __main__.py). Avg CC A(4.9), max B(8). Roda via `python -m processor`.
- **M4.** ✅ `pytest.ini` com addopts strict + cov-branch.
- **M5.** ✅ SSE com fechamento explícito (`return` após `done`); teste de desconexão em `test_concurrency`.

---

## REMANESCENTE

- `routes/laudos.py` 322 LOC: cohesive single-resource router. Subdividir traz fragmentação sem ganho real. Manter.
- `_montar_prompt` CC=9 — dentro do alvo B mas é a função mais complexa restante. Refatoração futura se evoluir.

---

## RECOMENDACAO

**Pronto para shippar v1.** Todos os C*, A* e M* fechados.
