"""Extract: lê arquivos raw e infere metadata a partir do slug."""
from __future__ import annotations

import re
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

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
