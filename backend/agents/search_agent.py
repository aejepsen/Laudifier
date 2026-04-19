# backend/agents/search_agent.py
"""
Busca de laudos de referência no Qdrant.
Índice especializado com filtros por especialidade e tipo de laudo.
"""

import asyncio
import logging
import os
import uuid

from fastembed import TextEmbedding
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Filter, FieldCondition, MatchValue,
    Distance, VectorParams, PointStruct,
)

logger = logging.getLogger(__name__)

QDRANT_URL  = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_KEY  = os.getenv("QDRANT_API_KEY", "")
COLLECTION  = os.getenv("QDRANT_COLLECTION", "laudos_medicos")
EMB_MODEL   = "intfloat/multilingual-e5-large"
EMB_DIM     = 1024

_model: TextEmbedding | None = None
_model_error: Exception | None = None
_qdrant_client: AsyncQdrantClient | None = None


def _get_qdrant_client() -> AsyncQdrantClient:
    """Singleton do AsyncQdrantClient — reutiliza conexão entre requests."""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = AsyncQdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_KEY or None,
            timeout=30,  # cross-region: Azure BR → Qdrant US East
        )
    return _qdrant_client


def _get_model() -> TextEmbedding:
    """Carrega o modelo uma única vez por processo (lazy singleton)."""
    global _model, _model_error
    if _model_error is not None:
        raise _model_error
    if _model is None:
        try:
            _model = TextEmbedding(
                model_name=EMB_MODEL,
                cache_dir=os.getenv("FASTEMBED_CACHE_DIR", "/home/app/.cache/fastembed"),
            )
        except Exception as e:
            _model_error = e
            logger.error(f"[SearchAgent] Falha ao carregar modelo {EMB_MODEL}: {e}")
            raise
    return _model


class LaudoSearchAgent:
    def __init__(self):
        self.qdrant = _get_qdrant_client()

    async def buscar_laudos_similares(
        self,
        query:         str,
        especialidade: str = "",
        tipo_laudo:    str = "",
        top:           int = 5,
    ) -> list[dict]:
        """
        Busca laudos similares no repositório com filtro por especialidade.
        Retorna lista vazia se o modelo de embedding não estiver disponível.
        """
        try:
            embedding = await self._embed(query)
        except Exception as e:
            logger.warning(f"[SearchAgent] Embedding indisponível, usando fallback Claude: {e}")
            return []

        filtro = self._build_filter(especialidade, tipo_laudo)

        try:
            response = await self.qdrant.query_points(
                collection_name=COLLECTION,
                query=embedding,
                query_filter=filtro,
                limit=top,
                with_payload=True,
                score_threshold=0.45,
            )
            results = response.points
            # Fallback sem filtro de especialidade se retornar vazio
            if not results and filtro is not None:
                logger.info("[SearchAgent] Busca filtrada vazia — tentando sem filtro de especialidade")
                response = await self.qdrant.query_points(
                    collection_name=COLLECTION,
                    query=embedding,
                    query_filter=None,
                    limit=top,
                    with_payload=True,
                    score_threshold=0.45,
                )
                results = response.points
            return [self._to_dict(r) for r in results]
        except Exception as e:
            logger.warning(f"[SearchAgent] Qdrant search falhou: {e}")
            return []

    async def _embed(self, text: str) -> list[float]:
        model = _get_model()
        # FastEmbed é síncrono — executa em thread pool para não bloquear o event loop
        # query_embed já aplica o prefixo "query: " internamente para modelos E5
        vec = await asyncio.to_thread(
            lambda: list(model.query_embed([text]))[0]
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

    async def buscar_laudos_do_medico(
        self,
        medico_id:     str,
        query:         str,
        especialidade: str = "",
        top:           int = 3,
    ) -> list[dict]:
        """
        Busca laudos aprovados pelo próprio médico no Qdrant.
        Retorna os mais similares à query atual — usados como referência prioritária.
        """
        try:
            embedding = await self._embed(query)
        except Exception:
            return []

        conditions = [FieldCondition(key="medico_id", match=MatchValue(value=medico_id))]
        if especialidade:
            conditions.append(
                FieldCondition(key="especialidade", match=MatchValue(value=especialidade.lower()))
            )

        try:
            response = await self.qdrant.query_points(
                collection_name=COLLECTION,
                query=embedding,
                query_filter=Filter(must=conditions),
                limit=top,
                with_payload=True,
                score_threshold=0.40,
            )
            return [self._to_dict(r) for r in response.points]
        except Exception as e:
            logger.warning(f"[SearchAgent] buscar_laudos_do_medico falhou: {e}")
            return []

    async def indexar_laudo_aprovado(
        self,
        laudo_id:      str,
        medico_id:     str,
        laudo_text:    str,
        especialidade: str,
        solicitacao:   str,
    ) -> None:
        """
        Indexa um laudo aprovado pelo médico no Qdrant.
        Usado para personalização progressiva: laudos futuros buscam estes como referência.
        """
        try:
            model = _get_model()
            chunks = self._chunk_text(laudo_text)
            points = []
            for i, chunk in enumerate(chunks):
                vec = await asyncio.to_thread(
                    lambda c=chunk: list(model.passage_embed([c]))[0]
                )
                points.append(PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"medico:{medico_id}:{laudo_id}:{i}")),
                    vector=vec.tolist(),
                    payload={
                        "content":       chunk,
                        "source_name":   f"medico_{medico_id}_{laudo_id[:8]}",
                        "especialidade": especialidade.lower(),
                        "tipo_laudo":    solicitacao[:80],
                        "source":        "medico_aprovado",
                        "medico_id":     medico_id,
                        "chunk_index":   i,
                    },
                ))
            await self.qdrant.upsert(collection_name=COLLECTION, points=points)
            logger.info(f"[SearchAgent] Laudo {laudo_id} indexado ({len(points)} chunks) para médico {medico_id}")
        except Exception as e:
            logger.error(f"[SearchAgent] indexar_laudo_aprovado falhou: {e}")

    @staticmethod
    def _chunk_text(text: str, size: int = 600, overlap: int = 30) -> list[str]:
        words = text.split()
        chunks, cur = [], []
        for w in words:
            cur.append(w)
            if len(" ".join(cur)) >= size:
                chunks.append(" ".join(cur))
                cur = cur[-overlap:]
        if cur:
            chunks.append(" ".join(cur))
        return chunks

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
    client = AsyncQdrantClient(url=QDRANT_URL, api_key=QDRANT_KEY or None, timeout=30)

    await client.recreate_collection(
        collection_name=COLLECTION,
        vectors_config={"dense": VectorParams(size=EMB_DIM, distance=Distance.COSINE)},
    )

    for field in ["especialidade", "tipo_laudo", "source_name", "modalidade", "medico_id", "source"]:
        await client.create_payload_index(COLLECTION, field, "keyword")

    print(f"✅ Coleção '{COLLECTION}' criada no Qdrant")
