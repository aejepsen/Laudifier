"""Transform: parsing de seções, splitting de laudos e extração de frases."""
from __future__ import annotations

import re

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
# Laudo splitter
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
    cleaned = NOISE_STRIP_RE.sub("", body).strip()
    if not cleaned:
        cleaned = body

    parts = FRASES_HEADING_RE.split(cleaned)
    frases = []
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
