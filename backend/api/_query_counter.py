"""
Contador de queries externas por request — detecta N+1 em runtime.

Uso:
    from ._query_counter import track_query, reset_query_counter, get_query_count
    track_query("qdrant.query_points")  # no wrapper do client
    track_query("mem0.search")

O middleware `query_counter_middleware` reseta o contador por request e loga
`warning` quando excede `QUERY_THRESHOLD` — útil em APM para flagar endpoints
que disparam muitas calls externas (sinal de N+1).
"""
from __future__ import annotations

import contextvars
import logging
import os
from collections import Counter

logger = logging.getLogger(__name__)

QUERY_THRESHOLD = int(os.getenv("QUERY_COUNT_THRESHOLD", "10"))

_counter: contextvars.ContextVar[Counter[str] | None] = contextvars.ContextVar(
    "laudifier_query_counter", default=None,
)


def reset_query_counter() -> None:
    _counter.set(Counter())


def track_query(label: str) -> None:
    """Incrementa o contador da request atual. No-op se fora de contexto HTTP."""
    c = _counter.get()
    if c is not None:
        c[label] += 1


def get_query_count() -> Counter[str]:
    return _counter.get() or Counter()


def log_if_over_threshold(path: str) -> None:
    c = _counter.get()
    if c is None:
        return
    total = sum(c.values())
    if total > QUERY_THRESHOLD:
        logger.warning(
            "[N+1] %s disparou %d queries externas (threshold=%d): %s",
            path, total, QUERY_THRESHOLD, dict(c),
        )
