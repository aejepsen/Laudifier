"""
pipeline/seed_repositorio.py
Ingere os 125 laudos de referência em /data/laudos/copiados no Qdrant.

Uso:
    # a partir de laudifier/backend/
    python -m pipeline.seed_repositorio

Variáveis de ambiente necessárias (copie de .env.example):
    OPENAI_API_KEY, QDRANT_URL, QDRANT_API_KEY (opcional)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────

DATA_DIR    = Path(__file__).parent.parent.parent.parent / "data" / "laudos" / "copiados"
QDRANT_URL  = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_KEY  = os.getenv("QDRANT_API_KEY") or None
COLLECTION  = os.getenv("QDRANT_COLLECTION", "laudos_medicos")
OAI_KEY     = os.getenv("OPENAI_API_KEY")
EMB_MODEL   = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
EMB_DIM     = 3072   # text-embedding-3-large
BATCH_SIZE  = 40     # chunks por chamada à API de embeddings
SYSTEM_ID   = "seed-script"


# ─── Inferência de especialidade/tipo a partir do nome do arquivo ─────────────

def _inferir(filename: str) -> tuple[str, str]:
    """Retorna (especialidade, tipo_laudo) com base no nome do arquivo."""
    nome = filename.lower()

    # ── Tipo (modalidade) ──
    if re.search(r"\bressonân|ressonancia|\brm\b", nome):
        tipo = "ressonancia"
    elif re.search(r"\btomografia|\btc\b|tomograf", nome):
        tipo = "tomografia"
    elif re.search(r"ultrassonografia|ultrassom|\beco\b", nome):
        tipo = "ultrassonografia"
    elif "pet" in nome:
        tipo = "pet_ct"
    elif re.search(r"radiografia|radiograf|\brx\b", nome):
        tipo = "radiografia"
    elif "mamografia" in nome:
        tipo = "mamografia"
    elif re.search(r"angio|angiorressonân|angiotomografia", nome):
        tipo = "angiotomografia"
    elif re.search(r"escore.*c[aá]lcio|c[aá]lcio.*escore", nome):
        tipo = "escore_calcio"
    elif "colangiografia" in nome:
        tipo = "colangiografia"
    elif "histerossalpingografia" in nome:
        tipo = "histerossalpingografia"
    elif "densitometria" in nome:
        tipo = "densitometria"
    elif re.search(r"defecograma|esvaziam", nome):
        tipo = "defecograma"
    elif re.search(r"deglutograma|esofagografia|esofagograma|eed\b", nome):
        tipo = "esofagografia"
    else:
        tipo = "outro"

    # ── Especialidade ──
    if re.search(r"cr[aâ]nio|neuro|isquemia|hemorrag|leucodistrofia|metab[oó]l|epilepsia|atrofia|encéfalo|encefalo|hip[oó]fise|amnesia|facomatose|desmieliniz|wernicke|avch", nome):
        esp = "neurologia"
    elif re.search(r"coluna|plexo lombar|medula", nome):
        esp = "ortopedia"
    elif re.search(r"card[ií]ac|escore.*c[aá]lcio|pericárdio|pericardio", nome):
        esp = "cardiologia"
    elif re.search(r"\bmama\b|mamografia", nome):
        esp = "mastologia"
    elif re.search(r"gestação|gestacao|\bútero\b|\bovário\b|pelve feminina|histerossalpingografia", nome):
        esp = "ginecologia"
    elif re.search(r"pelve masculina|próstata|prostata", nome):
        esp = "urologia"
    elif re.search(r"msk|musculoesquelético|musculoesqueletico|joelho|cotovelo|\bmão\b|membros|artérias temporais|atm\b|partes moles|kienbock|trauma.*membro|região inguinal", nome):
        esp = "musculoesqueletico"
    elif re.search(r"tórax|torax|pulmão|pulm|mediastino|empie|timo\b", nome):
        esp = "pneumologia"
    elif re.search(r"laringe|traqueia|cabeça.*pescoço|cabeca.*pescoco|cabeça e pescoço|craniofacial|calota|glândulas", nome):
        esp = "cabeca_e_pescoco"
    elif re.search(r"\bpet\b|adrenal|adenoma|nuclear|dotatate|pib\b|neop", nome):
        esp = "medicina_nuclear"
    elif re.search(r"angio.*corp|artér.*corpo|veia.*cava|aorta|vasc", nome):
        esp = "radiologia_vascular"
    elif re.search(r"abdome|fígado|figado|baço|baco|pâncreas|pancreas|bexiga|mesentério|mesenterio|colangiografia|deglutograma|esofagograma|eed\b|densitometria|defecograma|histeross", nome):
        esp = "gastroenterologia"
    else:
        esp = "radiologia"

    return esp, tipo


# ─── Qdrant setup ─────────────────────────────────────────────────────────────

def _garantir_collection(client: QdrantClient) -> None:
    existentes = {c.name for c in client.get_collections().collections}
    if COLLECTION not in existentes:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config={"dense": VectorParams(size=EMB_DIM, distance=Distance.COSINE)},
        )
        log.info("Collection '%s' criada (%d dims, cosine).", COLLECTION, EMB_DIM)
    else:
        log.info("Collection '%s' já existe — upsert incremental.", COLLECTION)


# ─── Chunking ─────────────────────────────────────────────────────────────────

def _chunk(texto: str, filename: str, esp: str, tipo: str) -> list[dict]:
    """Divide o laudo por seções em maiúsculas (ACHADOS:, IMPRESSÃO:, etc.)."""
    secoes = re.split(r"\n(?=[A-ZÁÉÍÓÚ ]{4,}:)", texto)
    chunks = []
    for sec in secoes:
        sec = sec.strip()
        if len(sec) >= 80:
            chunks.append({
                "id":            uuid.uuid4().hex,
                "content":       sec[:4000],  # limite de segurança
                "source_name":   filename,
                "especialidade": esp,
                "tipo_laudo":    tipo,
                "indexado_por":  SYSTEM_ID,
                "aprovado":      True,
            })
    # fallback: laudo sem seções marcadas vira um chunk único
    if not chunks:
        chunks.append({
            "id":            uuid.uuid4().hex,
            "content":       texto[:4000],
            "source_name":   filename,
            "especialidade": esp,
            "tipo_laudo":    tipo,
            "indexado_por":  SYSTEM_ID,
            "aprovado":      True,
        })
    return chunks


# ─── Embeddings + upsert ──────────────────────────────────────────────────────

def _indexar(chunks: list[dict], oai: OpenAI, qdrant: QdrantClient) -> int:
    """Gera embeddings em lotes e upserta no Qdrant. Retorna nº de pontos indexados."""
    total = 0
    for i in range(0, len(chunks), BATCH_SIZE):
        lote   = chunks[i : i + BATCH_SIZE]
        textos = [c["content"] for c in lote]

        resp = oai.embeddings.create(input=textos, model=EMB_MODEL)
        embs = [e.embedding for e in resp.data]

        points = [
            PointStruct(id=c["id"], vector={"dense": emb}, payload=c)
            for c, emb in zip(lote, embs)
        ]
        qdrant.upsert(collection_name=COLLECTION, points=points)
        total += len(points)

    return total


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    if not OAI_KEY:
        raise EnvironmentError("OPENAI_API_KEY não definida. Copie .env.example para .env e preencha.")

    arquivos = sorted(DATA_DIR.glob("*.txt"))
    if not arquivos:
        raise FileNotFoundError(f"Nenhum .txt encontrado em {DATA_DIR}")

    log.info("Iniciando seed: %d arquivos em %s", len(arquivos), DATA_DIR)

    oai    = OpenAI(api_key=OAI_KEY)
    qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_KEY)
    _garantir_collection(qdrant)

    total_chunks = 0
    erros: list[str] = []

    for idx, arq in enumerate(arquivos, 1):
        try:
            texto = arq.read_text(encoding="utf-8", errors="ignore").strip()
            if not texto:
                log.warning("[%d/%d] Vazio — pulando: %s", idx, len(arquivos), arq.name)
                continue

            esp, tipo = _inferir(arq.name)
            chunks     = _chunk(texto, arq.name, esp, tipo)
            n          = _indexar(chunks, oai, qdrant)
            total_chunks += n

            log.info("[%d/%d] ✓ %d chunk(s) | %s | %s — %s",
                     idx, len(arquivos), n, esp, tipo, arq.name)

        except Exception as exc:
            log.error("[%d/%d] ✗ ERRO em '%s': %s", idx, len(arquivos), arq.name, exc)
            erros.append(arq.name)

    log.info("─" * 60)
    log.info("Seed concluído: %d chunks indexados de %d arquivos.",
             total_chunks, len(arquivos) - len(erros))
    if erros:
        log.warning("%d arquivo(s) com erro: %s", len(erros), erros)
    else:
        log.info("Zero erros.")


if __name__ == "__main__":
    asyncio.run(main())
