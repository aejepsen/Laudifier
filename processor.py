"""
Processor: transforma data/raw/ nos três formatos de destino.

Outputs:
  data/rag/chunks.jsonl       — chunks com metadata para Qdrant
  data/finetune/pairs.jsonl   — pares input/output para fine-tuning
  data/templates/templates.json — laudos estruturados por modalidade/região
"""
import json
import re
from pathlib import Path

RAW_DIR       = Path(__file__).parent / "data" / "raw"
RAG_DIR       = Path(__file__).parent / "data" / "rag"
FINETUNE_DIR  = Path(__file__).parent / "data" / "finetune"
TEMPLATES_DIR = Path(__file__).parent / "data" / "templates"

for d in [RAG_DIR, FINETUNE_DIR, TEMPLATES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Metadata extraction from slug
# ---------------------------------------------------------------------------

MODALIDADE_MAP = [
    (r"\brm\b|ressonancia|ressonânc",               "RM"),
    (r"\btc\b|tomografia|angiotomografia|colangiotomografia|enterotomografia|colonografia",
                                                     "TC"),
    (r"doppler|us-|us__|us-geral|us-obstetric|ultrassonog",
                                                     "US"),
    (r"mamografia",                                  "Mamografia"),
    (r"densitometria",                               "Densitometria"),
    (r"pet",                                         "PET-CT"),
    (r"radiografia|rx\b",                            "RX"),
    (r"cintilografia",                               "Cintilografia"),
]

REGIAO_MAP = [
    (r"cranio|crânio|neuro|cerebr",                  "crânio"),
    (r"cabeca|cabeça|pescoco|pescoço|cervic|orbita|seio|temporal|atm", "cabeça-pescoço"),
    (r"abdome|abdômen|fígado|hepat|pancr|baço|renal|rim|urin",        "abdome"),
    (r"pelve|prostat|uter|ovar|endometr|bexig|canal-anal|bolsa-estr",  "pelve"),
    (r"torax|tórax|pulmao|pulmão|cardio|coração|aorta",               "tórax"),
    (r"mama|mamas",                                  "mama"),
    (r"coluna",                                      "coluna"),
    (r"msk|musculo|musculoes|ombro|joelho|quadril|tornozelo|punho|mao|cotovelo|pe\b|plexo|membro",
                                                     "musculoesquelético"),
    (r"obstetric|fetal|placenta|gestac",             "obstétrico"),
    (r"doppler-arterial|doppler-venoso|doppler-carotid|doppler-renal|doppler-vci",
                                                     "vascular"),
    (r"penian|escrot",                               "pelve-masculina"),
    (r"corpo-inteiro|mieloma|estadiamento",          "corpo-inteiro"),
    (r"dental|mandibul|maxila",                      "dental"),
    (r"pet|petct",                                   "corpo-inteiro"),
]

CATEGORIA_MAP = [
    (r"frases",       "frases"),
    (r"modelo",       "modelo-laudo"),
    (r"protocolo",    "protocolo"),
    (r"acervo",       "acervo"),
    (r"procedimento", "procedimento"),
    (r"doppler",      "doppler"),
    (r"preparo",      "preparo"),
    (r"medidas",      "referencia"),
]


def extract_metadata(slug: str) -> dict:
    s = slug.lower()
    modalidade = "Geral"
    for pattern, value in MODALIDADE_MAP:
        if re.search(pattern, s):
            modalidade = value
            break

    regiao = "geral"
    for pattern, value in REGIAO_MAP:
        if re.search(pattern, s):
            regiao = value
            break

    categoria = "referencia"
    for pattern, value in CATEGORIA_MAP:
        if re.search(pattern, s):
            categoria = value
            break

    return {"modalidade": modalidade, "regiao": regiao, "categoria": categoria}


# ---------------------------------------------------------------------------
# Section parser for laudos
# ---------------------------------------------------------------------------

SECTION_RE = re.compile(
    r"(TÉCNICA|TECNICA|INDICAÇÃO|INDICACAO|INDICAÇÃO CLÍNICA|INDICACAO CLINICA"
    r"|ANÁLISE|ANALISE|OPINIÃO|OPINIAO|DESCRIÇÃO|DESCRICAO|MÉTODO|METODO"
    r"|PROCEDIMENTO|CONTRASTE):"
)

SECTION_NORMALIZE = {
    "TECNICA": "TÉCNICA",
    "INDICACAO": "INDICAÇÃO",
    "INDICACAO CLINICA": "INDICAÇÃO CLÍNICA",
    "ANALISE": "ANÁLISE",
    "OPINIAO": "OPINIÃO",
    "DESCRICAO": "DESCRIÇÃO",
    "METODO": "MÉTODO",
}


def parse_sections(text: str) -> dict[str, str]:
    """Divide o texto do laudo nas seções TÉCNICA / ANÁLISE / OPINIÃO etc."""
    parts = SECTION_RE.split(text)
    sections: dict[str, str] = {}
    i = 1
    while i < len(parts) - 1:
        key = SECTION_NORMALIZE.get(parts[i].strip(), parts[i].strip())
        value = parts[i + 1].strip() if i + 1 < len(parts) else ""
        sections[key] = value
        i += 2
    return sections


# ---------------------------------------------------------------------------
# Laudo splitter (same logic as splitter.py)
# ---------------------------------------------------------------------------

MARKER_RE = re.compile(
    # Com dois-pontos (formato moderno)
    r"TÉCNICA:|INDICAÇÃO:|INDICAÇÃO CLÍNICA:|ANÁLISE:|DESCRIÇÃO:|MÉTODO:"
    r"|PROCEDIMENTO:|TECNICA:|INDICACAO:|ANALISE:|OPINIAO:|RELATÓRIO:"
    # Sem dois-pontos (formato antigo — coluna, crânio-rm, tórax, msk-tc)
    r"|(?<=[A-ZÁÉÍÓÚÀÃÕÂÊÔÜÇÑ0-9\)])(TÉCNICA|TECNICA|MÉTODO|METODO"
    r"|ANÁLISE|ANALISE|OPINIÃO|OPINIAO|RELATÓRIO|RELATORIO)(?=[A-Z])"
)

TITLE_START_RE = re.compile(
    r"(RESSONÂNC|RESSONANC|TOMOGRAFIA|ANGIOTOMOGRAFIA|COLANGIOTOMOGRAFIA"
    r"|ULTRASSONOGRAFI|ULTRASSOM\b|MAMOGRAFIA|DENSITOMETRIA|RADIOGRAFIA"
    r"|CINTILOGRAFIA|ANGIORRESS|COLANGIORRESS|ENTERORRESS|ELASTOGRAFIA"
    r"|ECOCARDIOGRAFIA|ARTERIOGRAFIA|FLEBOGRAFIA|HISTEROSSALPINGOGRAFIA"
    r"|LINFOCINTIGRAFIA|ESOFAGOGRAMA|ENEMA|URETROCISTOGRAFIA|UROGRAFIA"
    r"|PET.?CT|PET.?RM|PET.?TC|MIELOGRAFIA|SIALOGRAFIA"
    r"|TOMOSÍNTESE|FLUOROSCOPIA|DEFECOGRAFIA)",
    re.IGNORECASE,
)

UPPER_TITLE_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "ÁÉÍÓÚÀÃÕÂÊÔÜÇÑ"
    " -/()\u00c0\u00c1\u00c2\u00c3\u00c4\u00c9\u00ca\u00cd\u00d3\u00d4\u00d5\u00da\u00dc\u00c7"
    "0123456789.,ºª"
)


def find_laudo_splits(body: str) -> list[tuple[int, str]]:
    results: list[tuple[int, str]] = []
    seen: set[int] = set()

    for mm in MARKER_RE.finditer(body):
        mp = mm.start()
        i = mp - 1
        limit = max(0, mp - 300)
        chars: list[str] = []
        while i >= limit:
            ch = body[i]
            if ch in UPPER_TITLE_CHARS:
                chars.append(ch)
                i -= 1
            else:
                break
        if not chars:
            continue
        raw = "".join(reversed(chars)).strip()
        kw = TITLE_START_RE.search(raw)
        if not kw:
            continue
        title = raw[kw.start():].strip()
        if len(title) < 10:
            continue
        title_start = (i + 1) + kw.start()
        if title_start in seen:
            continue
        seen.add(title_start)
        results.append((title_start, title))

    results.sort(key=lambda x: x[0])
    return results


def split_into_laudos(body: str, meta: dict) -> list[dict]:
    splits = find_laudo_splits(body)
    if not splits:
        return []

    laudos = []
    for idx, (start, title) in enumerate(splits):
        end = splits[idx + 1][0] if idx + 1 < len(splits) else len(body)
        chunk_text = body[start:end].strip()

        content = chunk_text[len(title):].strip() if chunk_text.startswith(title) else chunk_text
        content = content.replace("\xa0", " ").strip()

        sections = parse_sections(content)

        tecnica  = sections.get("TÉCNICA", sections.get("TECNICA", ""))
        analise  = sections.get("ANÁLISE", sections.get("ANALISE", ""))
        opiniao  = sections.get("OPINIÃO", sections.get("OPINIAO", ""))
        indicacao = sections.get("INDICAÇÃO", sections.get("INDICAÇÃO CLÍNICA", ""))

        full_text = f"{title}\n{content}"

        if len(full_text.split()) < 20:
            continue

        laudos.append({
            "titulo":    title,
            "tecnica":   tecnica,
            "indicacao": indicacao,
            "analise":   analise,
            "opiniao":   opiniao,
            "full_text": full_text,
            "words":     len(full_text.split()),
            **meta,
        })

    return laudos


# ---------------------------------------------------------------------------
# Frases parser
# ---------------------------------------------------------------------------

# All-caps heading in frases pages (pathology/region names)
FRASES_HEADING_RE = re.compile(
    r"(?<![A-ZÁÉÍÓÚÀÃÕÂÊÔÜÇÑ])([A-ZÁÉÍÓÚÀÃÕÂÊÔÜÇÑ][A-ZÁÉÍÓÚÀÃÕÂÊÔÜÇÑ\s\-\/]{4,59})"
    r"(?=[A-Z][a-záéíóúàãõâêôüçñ])"
)

NOISE_STRIP_RE = re.compile(
    r"^.*?(?:Compêndio da Radiologia|compendioradiologia\.com)[^A-ZÁÉÍÓÚÀÃÕÂÊÔÜÇÑ]*",
    re.DOTALL | re.IGNORECASE,
)


def parse_frases(body: str, meta: dict, source_url: str, source_slug: str) -> list[dict]:
    """Extrai frases diagnósticas de páginas frases-*."""
    # Remove navigation noise at the start
    cleaned = NOISE_STRIP_RE.sub("", body).strip()
    if not cleaned:
        cleaned = body

    # Split by all-caps headings
    parts = FRASES_HEADING_RE.split(cleaned)
    frases = []

    i = 0
    # First chunk might be before any heading
    preamble = parts[0].strip() if parts else ""
    i = 1

    while i < len(parts) - 1:
        heading = parts[i].strip()
        text = parts[i + 1].strip() if i + 1 < len(parts) else ""

        if len(text) > 20:
            frases.append({
                "heading":    heading,
                "text":       text,
                "full_text":  f"{heading}\n{text}",
                "source_url": source_url,
                "source_slug": source_slug,
                "words":      len(text.split()),
                **meta,
            })
        i += 2

    # If no headings found, treat full page as one chunk
    if not frases and len(cleaned) > 100:
        frases.append({
            "heading":    source_slug,
            "text":       cleaned,
            "full_text":  cleaned,
            "source_url": source_url,
            "source_slug": source_slug,
            "words":      len(cleaned.split()),
            **meta,
        })

    return frases


# ---------------------------------------------------------------------------
# File loader
# ---------------------------------------------------------------------------

# Remove navigation prefix that Playwright captures before the actual content
NAV_PREFIX_RE = re.compile(
    r"^.*?(?:Compêndio da Radiologia|compendioradiologia\.com\s*Link\s*Compêndio da Radiologia)"
    r"[^A-ZÁÉÍÓÚÀÃÕÂÊÔÜÇÑA-Za-z]*",
    re.DOTALL | re.IGNORECASE,
)


def load_raw(path: Path) -> tuple[str, str, str]:
    """Returns (source_url, source_slug, body)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    source_url  = lines[0].replace("URL: ", "").strip()  if lines else ""
    source_slug = lines[1].replace("SLUG: ", "").strip() if len(lines) > 1 else ""
    sep = next((i for i, l in enumerate(lines) if l.startswith("=" * 10)), 2)

    # Content is typically a single large line — join all content lines
    raw_body = " ".join(l.strip() for l in lines[sep + 1:] if l.strip())
    raw_body = raw_body.replace("\xa0", " ")

    # Strip navigation noise from the beginning
    body = NAV_PREFIX_RE.sub("", raw_body).strip()
    if not body:
        body = raw_body  # fallback if regex over-stripped

    return source_url, source_slug, body


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------

def main():
    raw_files = sorted(RAW_DIR.glob("*.txt"))
    print(f"Arquivos raw: {len(raw_files)}")

    all_laudos: list[dict] = []
    all_frases: list[dict] = []

    for path in raw_files:
        source_url, source_slug, body = load_raw(path)
        meta = extract_metadata(source_slug)
        meta["source_url"]  = source_url
        meta["source_slug"] = source_slug

        if meta["categoria"] == "modelo-laudo" or meta["categoria"] == "doppler":
            # Try to split into individual laudos
            laudos = split_into_laudos(body, meta)
            if laudos:
                all_laudos.extend(laudos)
                print(f"  [laudo {len(laudos):3}] {path.name[:65]}")
                continue

        if meta["categoria"] == "frases":
            frases = parse_frases(body, meta, source_url, source_slug)
            if frases:
                all_frases.extend(frases)
                print(f"  [frase {len(frases):3}] {path.name[:65]}")
                continue

        # Fallback: treat whole page as one chunk (protocols, reference, US models, etc.)
        laudos = split_into_laudos(body, meta)
        if laudos:
            all_laudos.extend(laudos)
            print(f"  [misc  {len(laudos):3}] {path.name[:65]}")

    print(f"\nLaudos: {len(all_laudos)}  |  Frases: {len(all_frases)}")

    # -------------------------------------------------------------------
    # OUTPUT 1: Templates JSON
    # -------------------------------------------------------------------
    templates = [
        {
            "titulo":    l["titulo"],
            "modalidade": l["modalidade"],
            "regiao":    l["regiao"],
            "categoria": l["categoria"],
            "tecnica":   l["tecnica"],
            "indicacao": l["indicacao"],
            "analise":   l["analise"],
            "opiniao":   l["opiniao"],
            "source_url": l["source_url"],
            "words":     l["words"],
        }
        for l in all_laudos
    ]

    # Group by modalidade/regiao
    grouped: dict = {}
    for t in templates:
        key = f"{t['modalidade']} / {t['regiao']}"
        grouped.setdefault(key, []).append(t)

    templates_out = {
        "total": len(templates),
        "por_modalidade_regiao": {k: v for k, v in sorted(grouped.items())},
    }
    (TEMPLATES_DIR / "templates.json").write_text(
        json.dumps(templates_out, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # -------------------------------------------------------------------
    # OUTPUT 2: Fine-tuning JSONL
    # -------------------------------------------------------------------
    finetune_records = []

    SYSTEM_PROMPT = (
        "Você é um assistente especializado em radiologia médica. "
        "Gere laudos radiológicos completos e precisos em português brasileiro, "
        "seguindo o padrão do Compêndio da Radiologia."
    )

    for l in all_laudos:
        if not l["tecnica"] and not l["analise"]:
            continue  # skip empty laudos

        # Pair 1: generate full laudo given title + indicação
        user_prompt = f"Gere um laudo de {l['titulo']}."
        if l["indicacao"]:
            user_prompt += f" Indicação: {l['indicacao']}"

        assistant_content = l["full_text"]

        finetune_records.append({
            "messages": [
                {"role": "system",    "content": SYSTEM_PROMPT},
                {"role": "user",      "content": user_prompt},
                {"role": "assistant", "content": assistant_content},
            ],
            "metadata": {
                "modalidade": l["modalidade"],
                "regiao":     l["regiao"],
                "titulo":     l["titulo"],
                "source_url": l["source_url"],
            },
        })

        # Pair 2: generate OPINIÃO from TÉCNICA + ANÁLISE (if both present)
        if l["tecnica"] and l["analise"] and l["opiniao"]:
            finetune_records.append({
                "messages": [
                    {"role": "system",    "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Com base neste laudo de {l['titulo']}, "
                            f"escreva a seção de OPINIÃO:\n\n"
                            f"TÉCNICA: {l['tecnica']}\n\n"
                            f"ANÁLISE: {l['analise']}"
                        ),
                    },
                    {"role": "assistant", "content": f"OPINIÃO: {l['opiniao']}"},
                ],
                "metadata": {
                    "modalidade": l["modalidade"],
                    "regiao":     l["regiao"],
                    "titulo":     l["titulo"],
                    "tipo":       "opiniao-generation",
                    "source_url": l["source_url"],
                },
            })

    # Frases as fine-tuning: "descreva achados de X em laudo de Y"
    for f in all_frases:
        if len(f["text"].split()) < 10:
            continue
        finetune_records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Escreva uma frase diagnóstica sobre {f['heading']} "
                        f"para laudo de {f['modalidade']} de {f['regiao']}."
                    ),
                },
                {"role": "assistant", "content": f["text"]},
            ],
            "metadata": {
                "modalidade": f["modalidade"],
                "regiao":     f["regiao"],
                "heading":    f["heading"],
                "tipo":       "frase-diagnostica",
                "source_url": f["source_url"],
            },
        })

    with open(FINETUNE_DIR / "pairs.jsonl", "w", encoding="utf-8") as fh:
        for rec in finetune_records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # -------------------------------------------------------------------
    # OUTPUT 3: RAG JSONL
    # -------------------------------------------------------------------
    rag_records = []

    # Laudos → one chunk per laudo (full context)
    for l in all_laudos:
        rag_records.append({
            "id":         f"laudo_{len(rag_records)}",
            "text":       l["full_text"],
            "tipo":       "modelo-laudo",
            "titulo":     l["titulo"],
            "modalidade": l["modalidade"],
            "regiao":     l["regiao"],
            "tecnica":    l["tecnica"],
            "analise":    l["analise"],
            "opiniao":    l["opiniao"],
            "source_url": l["source_url"],
            "words":      l["words"],
        })

    # Frases → one chunk per phrase (fine-grained retrieval)
    for f in all_frases:
        if len(f["text"].split()) < 8:
            continue
        rag_records.append({
            "id":         f"frase_{len(rag_records)}",
            "text":       f["full_text"],
            "tipo":       "frase-diagnostica",
            "titulo":     f["heading"],
            "modalidade": f["modalidade"],
            "regiao":     f["regiao"],
            "source_url": f["source_url"],
            "words":      f["words"],
        })

    with open(RAG_DIR / "chunks.jsonl", "w", encoding="utf-8") as fh:
        for rec in rag_records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # -------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------
    ft_words = sum(
        len(r["messages"][-1]["content"].split()) for r in finetune_records
    )
    rag_words = sum(r["words"] for r in rag_records)

    print(f"\n{'='*60}")
    print(f"TEMPLATES  → {TEMPLATES_DIR / 'templates.json'}")
    print(f"  {len(templates)} laudos em {len(grouped)} categorias")
    print()
    print(f"FINE-TUNING → {FINETUNE_DIR / 'pairs.jsonl'}")
    print(f"  {len(finetune_records)} pares  |  ~{ft_words:,} palavras")
    print()
    print(f"RAG         → {RAG_DIR / 'chunks.jsonl'}")
    print(f"  {len(rag_records)} chunks  |  ~{rag_words:,} palavras")
    print(f"    {sum(1 for r in rag_records if r['tipo']=='modelo-laudo')} laudos completos")
    print(f"    {sum(1 for r in rag_records if r['tipo']=='frase-diagnostica')} frases diagnósticas")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
