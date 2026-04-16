# backend/agents/search_agent.py
"""
Busca de laudos de referência no Qdrant.
Índice especializado com filtros por especialidade e tipo de laudo.
"""

import asyncio
import functools
import os

from sentence_transformers import SentenceTransformer
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Filter, FieldCondition, MatchValue,
    Distance, VectorParams,
)

QDRANT_URL  = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_KEY  = os.getenv("QDRANT_API_KEY", "")
COLLECTION  = os.getenv("QDRANT_COLLECTION", "laudos_medicos")
EMB_MODEL   = "intfloat/multilingual-e5-large"
EMB_DIM     = 1024


@functools.lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    """Carrega o modelo uma única vez por processo."""
    return SentenceTransformer(EMB_MODEL)


class LaudoSearchAgent:
    def __init__(self):
        self.qdrant = AsyncQdrantClient(url=QDRANT_URL, api_key=QDRANT_KEY or None)

    async def buscar_laudos_similares(
        self,
        query:         str,
        especialidade: str = "",
        tipo_laudo:    str = "",
        top:           int = 5,
    ) -> list[dict]:
        """
        Busca laudos similares no repositório com filtro por especialidade.
        Retorna lista de chunks com score de similaridade.
        """
        embedding = await self._embed(query)
        filtro    = self._build_filter(especialidade, tipo_laudo)

        results = await self.qdrant.search(
            collection_name=COLLECTION,
            query_vector=embedding,
            query_filter=filtro,
            limit=top,
            with_payload=True,
            score_threshold=0.45,
        )

        return [self._to_dict(r) for r in results]

    async def _embed(self, text: str) -> list[float]:
        model = _get_model()
        # SentenceTransformer é síncrono — executa em thread pool para não bloquear
        vec = await asyncio.to_thread(
            model.encode,
            f"query: {text}",   # prefixo E5
            normalize_embeddings=True,
        )
        return vec.tolist()

    def _build_filter(self, especialidade: str, tipo_laudo: str) -> Filter | None:
        conditions = []
        if especialidade:
            conditions.append(
                FieldCondition(key="especialidade",
                               match=MatchValue(value=especialidade.lower()))
            )
        if tipo_laudo:
            conditions.append(
                FieldCondition(key="tipo_laudo",
                               match=MatchValue(value=tipo_laudo.lower()))
            )
        return Filter(must=conditions) if conditions else None

    def _to_dict(self, point) -> dict:
        p = point.payload or {}
        return {
            "id":            str(point.id),
            "content":       p.get("content", ""),
            "source_name":   p.get("source_name", ""),
            "especialidade": p.get("especialidade", ""),
            "tipo_laudo":    p.get("tipo_laudo", ""),
            "score":         float(point.score),
        }


async def create_laudos_collection():
    """
    Cria a coleção Qdrant para laudos médicos.
    Execute uma vez: python -c "import asyncio; from backend.agents.search_agent import create_laudos_collection; asyncio.run(create_laudos_collection())"
    """
    client = AsyncQdrantClient(url=QDRANT_URL, api_key=QDRANT_KEY or None)

    await client.recreate_collection(
        collection_name=COLLECTION,
        vectors_config={"dense": VectorParams(size=EMB_DIM, distance=Distance.COSINE)},
    )

    for field in ["especialidade", "tipo_laudo", "source_name", "modalidade"]:
        await client.create_payload_index(COLLECTION, field, "keyword")

    print(f"✅ Coleção '{COLLECTION}' criada no Qdrant")
