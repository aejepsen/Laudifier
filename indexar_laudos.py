"""
Script de indexação dos laudos no Qdrant via backend (server-side).
O modelo de embedding roda no Container App — não precisa baixar nada localmente.

Uso:
    pip install httpx
    ADMIN_API_KEY=<chave> python indexar_laudos.py
    ou:
    ADMIN_API_KEY=<chave> BACKEND_URL=https://... python indexar_laudos.py
"""

import os
import sys
import math
from pathlib import Path

import httpx

# ── Configuração ──────────────────────────────────────────────────────────────

BACKEND_URL   = os.getenv("BACKEND_URL", "https://laudifier-production-backend.wonderfulsand-193c30c5.brazilsouth.azurecontainerapps.io")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
ENDPOINT      = f"{BACKEND_URL}/admin/pipeline/indexar"
STATUS_URL    = f"{BACKEND_URL}/admin/pipeline/status"

BASE_DIR  = Path(__file__).parent / "data" / "laudos"
RASPADOS  = BASE_DIR
COPIADOS  = BASE_DIR / "copiados"

BATCH_SIZE = 1           # 1 arquivo por request — evita 507 com arquivos grandes
TIMEOUT    = 300         # segundos — embedding 20 arquivos leva ~30-60s no CPU

# ── Helpers ───────────────────────────────────────────────────────────────────

def coletar_arquivos() -> list[dict]:
    arquivos = []
    for f in sorted(RASPADOS.glob("*.txt")):
        if f.is_file():
            arquivos.append({"path": f, "source": "raspado"})
    for f in sorted(COPIADOS.glob("*.txt")):
        if f.is_file():
            arquivos.append({"path": f, "source": "copiado"})
    return arquivos


def verificar_status(client: httpx.Client) -> int:
    try:
        r = client.get(STATUS_URL, headers={"x-admin-key": ADMIN_API_KEY}, timeout=30)
        r.raise_for_status()
        return r.json().get("points", 0)
    except Exception as e:
        print(f"⚠️  Não foi possível obter status: {e}")
        return -1


def indexar_batch(client: httpx.Client, batch: list[dict], source: str) -> dict:
    files_payload = []
    for item in batch:
        conteudo = item["path"].read_bytes()
        files_payload.append(
            ("files", (item["path"].name, conteudo, "text/plain"))
        )

    r = client.post(
        ENDPOINT,
        files=files_payload,
        data={"source": source},
        headers={"x-admin-key": ADMIN_API_KEY},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


# ── Principal ─────────────────────────────────────────────────────────────────

def main():
    if not ADMIN_API_KEY:
        print("❌ ADMIN_API_KEY não definida. Execute:")
        print("   export ADMIN_API_KEY=<chave>")
        sys.exit(1)

    print(f"🔌 Backend: {BACKEND_URL}")

    arquivos = coletar_arquivos()
    raspados = [a for a in arquivos if a["source"] == "raspado"]
    copiados = [a for a in arquivos if a["source"] == "copiado"]
    print(f"📂 {len(arquivos)} arquivos encontrados ({len(raspados)} raspados + {len(copiados)} copiados)")

    with httpx.Client() as client:
        pontos_antes = verificar_status(client)
        if pontos_antes >= 0:
            print(f"📊 Qdrant agora: {pontos_antes} pontos\n")

        total_chunks = 0
        total_erros  = 0

        # Indexar em batches por source para manter metadados corretos
        for source_label, grupo in [("raspado", raspados), ("copiado", copiados)]:
            if not grupo:
                continue
            n_batches = math.ceil(len(grupo) / BATCH_SIZE)
            print(f"📤 Indexando {len(grupo)} arquivos [{source_label}] em {n_batches} batches...")

            for i in range(n_batches):
                batch = grupo[i * BATCH_SIZE:(i + 1) * BATCH_SIZE]
                names = [b["path"].name[:40] for b in batch]
                print(f"  Batch {i+1}/{n_batches}: {names[0]}{'...' if len(names) > 1 else ''} (+{len(names)-1})")

                MAX_RETRIES = 3
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        res = indexar_batch(client, batch, source=source_label)
                        chunks = res.get("chunks_indexed", 0)
                        erros  = res.get("errors", [])
                        total_chunks += chunks
                        total_erros  += len(erros)
                        print(f"    ✅ {res.get('files_indexed', 0)} arquivos → {chunks} chunks")
                        for e in erros:
                            print(f"    ⚠️  {e['file']}: {e['error']}")
                        break  # sucesso — sai do loop de retry
                    except httpx.HTTPStatusError as e:
                        msg = f"HTTP {e.response.status_code}: {e.response.text[:150]}"
                        if attempt < MAX_RETRIES:
                            print(f"    ↩️  Tentativa {attempt}/{MAX_RETRIES} falhou ({msg}) — aguardando 10s...")
                            import time; time.sleep(10)
                        else:
                            print(f"    ❌ {msg}")
                            total_erros += len(batch)
                    except Exception as e:
                        msg = str(e)[:150]
                        if attempt < MAX_RETRIES:
                            print(f"    ↩️  Tentativa {attempt}/{MAX_RETRIES} falhou ({msg}) — aguardando 10s...")
                            import time; time.sleep(10)
                        else:
                            print(f"    ❌ {msg}")
                            total_erros += len(batch)

        pontos_depois = verificar_status(client)
        print(f"\n✅ Indexação concluída!")
        print(f"   Chunks indexados nessa rodada: {total_chunks}")
        print(f"   Erros:                         {total_erros}")
        print(f"   Total no Qdrant agora:         {pontos_depois}")


if __name__ == "__main__":
    main()
