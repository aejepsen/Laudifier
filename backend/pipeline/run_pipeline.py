# backend/pipeline/run_pipeline.py
"""
Pipeline de indexação de laudos no Qdrant.
Funções de chunking e extração de texto reutilizadas pelo agente de busca.
"""

import re
from pathlib import Path


_CHUNK_SIZE = 1500   # chars por chunk
_CHUNK_OVERLAP = 150


def _extrair_texto(filepath: str, filename: str) -> str:
    """Extrai texto de um arquivo (.txt, .pdf, .docx)."""
    ext = Path(filename).suffix.lower()

    if ext == ".txt":
        return Path(filepath).read_text(encoding="utf-8", errors="ignore")

    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(filepath)
        return "\n".join(p.extract_text() or "" for p in reader.pages)

    if ext in (".docx", ".doc"):
        from docx import Document
        doc = Document(filepath)
        return "\n".join(p.text for p in doc.paragraphs)

    # fallback: tenta ler como texto
    return Path(filepath).read_text(encoding="utf-8", errors="ignore")


def _chunk_laudo(
    texto: str,
    filename: str,
    especialidade: str,
    tipo_laudo: str,
    user_id: str,
) -> list[dict]:
    """
    Divide o texto do laudo em chunks com metadados para indexação no Qdrant.
    Laudos curtos retornam um único chunk; laudos longos são divididos por seção
    ou por tamanho quando não há seções explícitas.
    """
    if not texto.strip():
        return []

    # Tenta dividir por seções (linhas em MAIÚSCULAS com menos de 60 chars)
    section_pattern = re.compile(r'^([A-ZÁÉÍÓÚÂÊÔÃÕÇ\s/:]+):\s*$', re.MULTILINE)
    sections = section_pattern.split(texto.strip())

    chunks: list[str] = []

    if len(sections) > 1:
        # Reconstrói seções como "TÍTULO:\nconteúdo"
        i = 1
        while i < len(sections) - 1:
            title   = sections[i].strip()
            content = sections[i + 1].strip()
            if content:
                chunks.append(f"{title}:\n{content}")
            i += 2
    else:
        # Sem seções marcadas: divide por tamanho com overlap
        start = 0
        while start < len(texto):
            end = min(start + _CHUNK_SIZE, len(texto))
            chunks.append(texto[start:end])
            if end == len(texto):
                break
            start = end - _CHUNK_OVERLAP

    if not chunks:
        chunks = [texto.strip()]

    return [
        {
            "texto":        chunk,
            "filename":     filename,
            "especialidade": especialidade,
            "tipo_laudo":   tipo_laudo,
            "user_id":      user_id,
            "aprovado":     True,
        }
        for chunk in chunks
        if chunk.strip()
    ]
