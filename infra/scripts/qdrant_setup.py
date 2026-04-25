"""
Cria índices payload no Qdrant: medico_id (uuid), source (keyword).
Idempotente — Qdrant ignora criação duplicada via try/except.

Uso:
    .venv/bin/python infra/scripts/qdrant_setup.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Carrega .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import PayloadSchemaType

COLLECTION = os.getenv("QDRANT_COLLECTION", "laudos")
INDEXES: list[tuple[str, PayloadSchemaType]] = [
    ("medico_id",     PayloadSchemaType.KEYWORD),
    ("especialidade", PayloadSchemaType.KEYWORD),
    ("tipo_laudo",    PayloadSchemaType.KEYWORD),
    ("source",        PayloadSchemaType.KEYWORD),
    ("source_name",   PayloadSchemaType.KEYWORD),
    ("modalidade",    PayloadSchemaType.KEYWORD),
]


def main() -> int:
    url = os.getenv("QDRANT_URL")
    key = os.getenv("QDRANT_API_KEY")
    if not url:
        print("ERRO: QDRANT_URL ausente no .env", file=sys.stderr)
        return 1

    client = QdrantClient(url=url, api_key=key)

    try:
        client.get_collection(COLLECTION)
    except UnexpectedResponse as e:
        print(f"ERRO: collection '{COLLECTION}' não existe ({e}).", file=sys.stderr)
        print("       Crie a collection antes (ver pipeline_routes.py).", file=sys.stderr)
        return 2

    criados, existentes = [], []
    for field, schema in INDEXES:
        try:
            client.create_payload_index(
                collection_name=COLLECTION,
                field_name=field,
                field_schema=schema,
            )
            criados.append(field)
        except UnexpectedResponse as e:
            # Já existe — Qdrant retorna 4xx
            if "already exists" in str(e).lower() or e.status_code in (400, 409):
                existentes.append(field)
            else:
                print(f"FALHA em '{field}': {e}", file=sys.stderr)

    print(f"Criados:    {criados or '—'}")
    print(f"Existentes: {existentes or '—'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
