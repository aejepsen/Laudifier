# backend/agents/search_agent.py
"""
Busca de laudos de referência no Qdrant.
Índice especializado com filtros por especialidade e tipo de laudo.
"""

import os
from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Filter, FieldCondition, MatchValue, MatchAny,
    Distance, VectorParams, SparseVectorParams, SparseIndexParams,
)

QDRANT_URL  = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_KEY  = os.getenv("QDRANT_API_KEY", "")
COLLECTION  = os.getenv("QDRANT_COLLECTION", "laudos_medicos")
OAI_KEY     = os.getenv("OPENAI_API_KEY")
EMB_MODEL   = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
EMB_DIM     = int(os.getenv("EMBEDDING_DIMENSIONS", "3072"))


class LaudoSearchAgent:
    def __init__(self):
        self.qdrant = AsyncQdrantClient(url=QDRANT_URL, api_key=QDRANT_KEY or None)
        self.openai = AsyncOpenAI(api_key=OAI_KEY)

    async def buscar_laudos_similares(
        self,
        query:       str,
        especialidade: str = "",
        tipo_laudo:  str = "",
        top:         int = 5,
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
            score_threshold=0.45,   # ignora laudos muito diferentes
        )

        return [self._to_dict(r) for r in results]

    async def _embed(self, text: str) -> list[float]:
        r = await self.openai.embeddings.create(input=text[:8000], model=EMB_MODEL)
        return r.data[0].embedding

    def _build_filter(self, especialidade: str, tipo_laudo: str) -> Filter | None:
        conditions = []
        if especialidade:
            # Normaliza: "Radiologia" → "radiologia"
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

    # Índices para filtros rápidos por especialidade
    for field in ["especialidade", "tipo_laudo", "source_name", "modalidade"]:
        await client.create_payload_index(COLLECTION, field, "keyword")

    print(f"✅ Coleção '{COLLECTION}' criada no Qdrant")
