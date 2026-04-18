"""
Indexa laudos de data/laudos/copiados/ e data/laudos/sinteticos/ no Qdrant.
Classificação por tipo de exame: rm, tc, us, rx, mamografia, pet_ct, etc.

Uso: python indexar_copiados.py
"""
import os, uuid, time
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

BASE_DIR    = os.path.dirname(__file__)
QDRANT_URL  = os.getenv("QDRANT_URL",    "https://b8953933-ba84-42aa-88e9-6b35c4ac8971.us-east-1-1.aws.cloud.qdrant.io")
QDRANT_KEY  = os.getenv("QDRANT_API_KEY","eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.v43zD0y86l23-WWgubcr2BQv3jE1wUAu4bgguzooOsM")
COLLECTION  = "laudos_medicos"
CHUNK_SIZE  = 600
OVERLAP     = 30

DIRETORIOS = [
    (os.path.join(BASE_DIR, "data/laudos/sinteticos"),          "sintetico"),
    (os.path.join(BASE_DIR, "data/laudos/sinteticos_completos"),"sintetico_completo"),
    (os.path.join(BASE_DIR, "data/laudos/copiados"),            "copiados"),
]


def detectar_especialidade(fname: str) -> str:
    n = fname.upper().replace("_", " ").replace("-", " ")
    # Medicina nuclear
    if "PET" in n:                                              return "pet_ct"
    if "CINTILO" in n:                                         return "medicina_nuclear"
    # Cardiologia
    if any(x in n for x in ["CARDÍ","CARDIA","ECOCARDIO","ERGOM","ERGOESPIRO","ERGOESP"]):
        return "cardiologia"
    # Patologia / procedimento
    if any(x in n for x in ["BIOPSIA","BIO PSIA","HISTOL","CITOL"]):
        return "patologia"
    # Gastroenterologia
    if any(x in n for x in ["EED","ENEMA","ESOFAGO","COLONOSCOP","ENDOSCOP",
                             "TGI","TRÂNSITO","TRANSITO","DEFECOGRAMA","DEGLUTOGRAMA"]):
        return "gastroenterologia"
    # Tipos de imagem — específico antes de genérico
    if any(x in n for x in ["MAMOGRAFIA","MAMOGR"]):           return "mamografia"
    if "DENSITOMETRIA" in n:                                   return "densitometria"
    if any(x in n for x in ["RM ","RM_"," RM","RESSONÂNCIA","RESSONANCIA",
                             "ANGIORRESSONÂNCIA","ANGIORRESSONANCIA"]):
        return "rm"
    # "TC" pode aparecer em muitos nomes — checar prefixo ou termos específicos
    if n.startswith("TC ") or n.startswith("TC_") or \
       any(x in n for x in ["TOMOGRAFIA","ANGIOTOMOGRAFIA"]):  return "tc"
    if any(x in n for x in ["US ","US_"," US","ULTRASSOM","ULTRASSONOGRAFIA",
                             "DOPPLER","ECOGRAFIA"]):           return "us"
    if any(x in n for x in ["RX ","RX_"," RX","RADIOGRAFIA","RADIOGRAFIAS","RAIO X"]):
        return "rx"
    # Fallback: se começa com modalidade conhecida
    prefixo = n.split()[0] if n.split() else ""
    if prefixo in ("TC","RM","US","RX"):                       return prefixo.lower()
    return "rx"


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = OVERLAP) -> list[str]:
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


def main():
    print("Carregando modelo sentence-transformers (CPU)...")
    model  = SentenceTransformer("intfloat/multilingual-e5-large", device="cpu")
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_KEY, timeout=30)

    before = client.count(COLLECTION).count
    print(f"Pontos no Qdrant antes: {before}\n")

    total_files = total_chunks = 0

    for diretorio, source_label in DIRETORIOS:
        if not os.path.isdir(diretorio):
            print(f"[SKIP] Diretório não encontrado: {diretorio}")
            continue

        files = sorted(f for f in os.listdir(diretorio) if f.endswith(".txt"))
        print(f"=== {source_label.upper()} — {len(files)} arquivos ===")

        for i, fname in enumerate(files, 1):
            path = os.path.join(diretorio, fname)
            esp  = detectar_especialidade(fname)
            with open(path, encoding="utf-8", errors="ignore") as f:
                text = f.read().strip()
            if not text:
                print(f"  [{i:3d}/{len(files)}] VAZIO — {fname}")
                continue

            chunks = chunk_text(text)
            points = [
                PointStruct(
                    # UUID determinístico: re-runs são idempotentes via upsert
                    id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{source_label}:{fname}:{j}")),
                    vector=model.encode(f"passage: {chunk}", normalize_embeddings=True).tolist(),
                    payload={
                        "content":       chunk,
                        "source_name":   fname,
                        "especialidade": esp,
                        "tipo_laudo":    os.path.splitext(fname)[0][:80],
                        "chunk_index":   j,
                        "source":        source_label,
                    },
                )
                for j, chunk in enumerate(chunks)
            ]
            for attempt in range(4):
                try:
                    client.upsert(COLLECTION, points)
                    break
                except Exception as e:
                    if attempt == 3:
                        raise
                    wait = 2 ** attempt
                    print(f"  [retry {attempt+1}/3 em {wait}s] {e}")
                    time.sleep(wait)
            total_chunks += len(chunks)
            total_files  += 1
            print(f"  [{i:3d}/{len(files)}] {esp:18s} | {len(chunks):3d} chunks | {fname}")

        print()

    after = client.count(COLLECTION).count
    print(f"Finalizado: {after} pontos (+{after - before} | {total_chunks} chunks de {total_files} arquivos)")


if __name__ == "__main__":
    main()
