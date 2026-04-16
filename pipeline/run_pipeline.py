# pipeline/run_pipeline.py
"""
Pipeline de ingestão de laudos de referência no Qdrant.
Suporta PDF, DOCX e TXT de laudos médicos.
"""
import os, uuid, re, json
from pathlib import Path
import anthropic
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

QDRANT_URL  = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_KEY  = os.getenv("QDRANT_API_KEY", "")
COLLECTION  = os.getenv("QDRANT_COLLECTION", "laudos_medicos")
OAI_KEY     = os.getenv("OPENAI_API_KEY")
EMB_MODEL   = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
ANT_MODEL   = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")


async def ingerir_laudo(url: str, filename: str, especialidade: str, tipo_laudo: str, user_id: str):
    """
    Ingere um laudo de referência no repositório Qdrant.
    Extrai texto → enriquece com Claude → indexa com embedding.
    """
    print(f"📥 Ingerindo: {filename} | {especialidade}")

    # 1. Extrai texto
    texto = _extrair_texto(url, filename)
    if not texto.strip():
        print(f"⚠️ Arquivo sem conteúdo extraível: {filename}")
        return

    # 2. Enriquece com Claude (extrai estrutura do laudo)
    metadados = _extrair_metadados(texto, especialidade)
    tipo_detectado = metadados.get("tipo_laudo", tipo_laudo) or tipo_laudo

    # 3. Divide em chunks semânticos (um laudo pode ter várias seções)
    chunks = _chunk_laudo(texto, filename, especialidade, tipo_detectado, user_id)

    # 4. Gera embeddings e indexa
    _indexar_chunks(chunks)
    print(f"✅ {len(chunks)} chunks indexados de {filename}")


def _extrair_texto(path_or_url: str, filename: str) -> str:
    ext = Path(filename).suffix.lower()
    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(path_or_url)
            return "\n\n".join(p.extract_text() or "" for p in reader.pages)
        elif ext == ".docx":
            from docx import Document
            doc = Document(path_or_url)
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        else:
            return Path(path_or_url).read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        print(f"⚠️ Erro ao extrair texto de {filename}: {e}")
        return ""


def _extrair_metadados(texto: str, especialidade: str) -> dict:
    """Usa Claude Haiku para extrair metadados estruturados do laudo."""
    client = anthropic.Anthropic()
    try:
        resp = client.messages.create(
            model=ANT_MODEL, max_tokens=500,
            messages=[{"role": "user", "content": f"""Analise este laudo médico e extraia metadados.
Retorne APENAS JSON:
{{
  "tipo_laudo": "rx_torax|tomografia|ressonancia|eco|patologia|endoscopia|outro",
  "modalidade": "descrição curta do tipo de exame",
  "palavras_chave": ["lista", "de", "termos", "médicos", "chave"]
}}

LAUDO (primeiros 1000 chars):
{texto[:1000]}"""}]
        )
        content = re.sub(r'^```json?\s*|\s*```$', '', resp.content[0].text.strip())
        return json.loads(content)
    except Exception:
        return {"tipo_laudo": "outro", "modalidade": especialidade, "palavras_chave": []}


def _chunk_laudo(texto: str, filename: str, especialidade: str, tipo_laudo: str, user_id: str) -> list[dict]:
    """
    Divide o laudo em chunks por seção.
    Um laudo completo geralmente fica num chunk só (são textos curtos).
    Laudos longos (patologia, relatórios) são divididos por seção.
    """
    # Se o laudo for curto, indexa como um chunk único
    if len(texto) < 3000:
        return [{
            "id":            uuid.uuid4().hex,
            "content":       texto.strip(),
            "source_name":   filename,
            "especialidade": especialidade.lower(),
            "tipo_laudo":    tipo_laudo.lower(),
            "indexado_por":  user_id,
            "aprovado":      True,
        }]

    # Laudos longos: divide por seções (ACHADOS, IMPRESSÃO, etc.)
    secoes = re.split(r'\n(?=[A-ZÁÉÍÓÚ]{4,}:)', texto)
    chunks = []
    for sec in secoes:
        if len(sec.strip()) > 100:
            chunks.append({
                "id":            uuid.uuid4().hex,
                "content":       sec.strip(),
                "source_name":   filename,
                "especialidade": especialidade.lower(),
                "tipo_laudo":    tipo_laudo.lower(),
                "indexado_por":  user_id,
                "aprovado":      True,
            })
    return chunks or [{"id": uuid.uuid4().hex, "content": texto[:3000], "source_name": filename,
                       "especialidade": especialidade.lower(), "tipo_laudo": tipo_laudo.lower(),
                       "indexado_por": user_id, "aprovado": True}]


def _indexar_chunks(chunks: list[dict]):
    oai    = OpenAI(api_key=OAI_KEY)
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_KEY or None)
    texts  = [c["content"] for c in chunks]

    emb_resp   = oai.embeddings.create(input=texts, model=EMB_MODEL)
    embeddings = [e.embedding for e in emb_resp.data]

    points = [
        PointStruct(id=c["id"], vector={"dense": emb}, payload=c)
        for c, emb in zip(chunks, embeddings)
    ]
    client.upsert(collection_name=COLLECTION, points=points)
