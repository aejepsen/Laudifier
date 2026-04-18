"""
Splitter: divide cada arquivo de data/raw/ em laudos individuais.
Salva em data/laudos/<source_slug>__<titulo_normalizado>.txt

Estratégia:
  1. Encontra todas as posições de marcadores de seção (TÉCNICA:, INDICAÇÃO:, etc.)
  2. Para cada marcador, varre para trás até encontrar a keyword que inicia o título
     (RESSONÂNCIA, TOMOGRAFIA, ULTRASSONOGRAFIA, etc.)
  3. Tudo desde essa keyword até o próximo marcador é um laudo individual.
"""
import os
import re
import json
from pathlib import Path

RAW_DIR  = Path(__file__).parent / "data" / "raw"
OUT_DIR  = Path(__file__).parent / "data" / "laudos"
IDX_FILE = Path(__file__).parent / "data" / "index_laudos.json"

OUT_DIR.mkdir(parents=True, exist_ok=True)

# Marcadores que iniciam uma seção de laudo (vêm logo após o título)
MARKER_RE = re.compile(
    r"TÉCNICA:|INDICAÇÃO:|INDICAÇÃO CLÍNICA:|ANÁLISE:|DESCRIÇÃO:|MÉTODO:|PROCEDIMENTO:|TECNICA:"
)

# Keywords que INICIAM um título de laudo (todas em maiúsculas)
TITLE_START_RE = re.compile(
    r"(RESSONÂNC|RESSONANC|TOMOGRAFIA|ANGIOTOMOGRAFIA|COLANGIOTOMOGRAFIA|"
    r"ULTRASSONOGRAFI|ULTRASSOM\b|MAMOGRAFIA|DENSITOMETRIA|RADIOGRAFIA|"
    r"CINTILOGRAFIA|ANGIORRESS|COLANGIORRESS|ENTERORRESS|ELASTOGRAFIA|"
    r"ECOCARDIOGRAFIA|ARTERIOGRAFIA|FLEBOGRAFIA|HISTEROSSALPINGOGRAFIA|"
    r"LINFOCINTIGRAFIA|ESOFAGOGRAMA|ENEMA|URETROCISTOGRAFIA|UROGRAFIA|"
    r"PET.?CT|PET.?RM|PET.?TC|MIELOGRAFIA|SIALOGRAFIA|"
    r"TOMOSÍNTESE|FLUOROSCOPIA)",
    re.IGNORECASE,
)

# Ruído de navegação a remover no início do body
NAV_NOISE_RE = re.compile(
    r"^.*?(RESSONÂNC|RESSONANC|TOMOGRAFIA|ANGIOTOMOGRAFIA|COLANGIOTOMOGRAFIA|"
    r"ULTRASSONOGRAFI|ULTRASSOM\b|MAMOGRAFIA|DENSITOMETRIA|RADIOGRAFIA|"
    r"CINTILOGRAFIA|ANGIORRESS|COLANGIORRESS|ENTERORRESS|ELASTOGRAFIA|"
    r"ECOCARDIOGRAFIA|PET.?CT|PET.?RM|PET.?TC|MIELOGRAFIA|SIALOGRAFIA|"
    r"ARTERIOGRAFIA|FLEBOGRAFIA|TOMOSÍNTESE|FLUOROSCOPIA)",
    re.IGNORECASE | re.DOTALL,
)


def title_to_slug(title: str) -> str:
    slug = title.lower()
    for src, dst in [("á","a"),("à","a"),("ã","a"),("â","a"),("ä","a"),
                     ("é","e"),("è","e"),("ê","e"),("ë","e"),
                     ("í","i"),("ì","i"),("î","i"),
                     ("ó","o"),("ò","o"),("õ","o"),("ô","o"),
                     ("ú","u"),("ù","u"),("û","u"),("ü","u"),
                     ("ç","c"),("ñ","n")]:
        slug = slug.replace(src, dst)
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")[:80]


def clean_content(text: str) -> str:
    """Normaliza espaços e remove ruído."""
    text = text.replace("\xa0", " ")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    # Remove duplicatas consecutivas
    clean = [lines[0]] if lines else []
    for l in lines[1:]:
        if l != clean[-1]:
            clean.append(l)
    return "\n".join(clean)


UPPER_TITLE_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "ÁÉÍÓÚÀÃÕÂÊÔÜÇÑ"
    " -/()\u00c0\u00c1\u00c2\u00c3\u00c4\u00c5\u00c6\u00c7\u00c8\u00c9\u00ca\u00cb"
    "\u00cc\u00cd\u00ce\u00cf\u00d0\u00d1\u00d2\u00d3\u00d4\u00d5\u00d6\u00d8"
    "\u00d9\u00da\u00db\u00dc\u00dd\u00de"
    "0123456789.,ºª"
)


def find_title_starts(body: str) -> list[tuple[int, str]]:
    """
    Retorna lista de (posição_início_título, título_extraído).

    Estratégia: para cada marcador de seção, varre para TRÁS caractere a
    caractere coletando apenas chars de título (maiúsculas + espaço + pontuação
    simples). Para quando encontra um char de texto corrido (minúscula).
    Descarta candidatos sem keyword de laudo.
    """
    results: list[tuple[int, str]] = []
    seen_positions: set[int] = set()

    for marker_match in MARKER_RE.finditer(body):
        marker_pos = marker_match.start()

        # Varre para trás até 300 chars coletando chars válidos de título
        i = marker_pos - 1
        limit = max(0, marker_pos - 300)
        title_chars: list[str] = []

        while i >= limit:
            ch = body[i]
            if ch in UPPER_TITLE_CHARS:
                title_chars.append(ch)
                i -= 1
            else:
                break  # bateu em char de conteúdo (minúscula, etc.)

        if not title_chars:
            continue

        raw = "".join(reversed(title_chars)).strip()
        # Encontra a PRIMEIRA keyword no raw → tudo a partir dela é o título real
        kw = TITLE_START_RE.search(raw)
        if not kw:
            continue
        title = raw[kw.start():].strip()
        if len(title) < 10:
            continue

        # Recalcula o título_start para corresponder à posição real no body
        # (i+1 = fim do scan, raw começa ali; kw.start() = offset dentro do raw)
        scan_start = i + 1  # posição do primeiro char coletado no body
        title_start = scan_start + kw.start()
        if title_start in seen_positions:
            continue
        seen_positions.add(title_start)

        results.append((title_start, title))

    results.sort(key=lambda x: x[0])
    return results


def split_file(raw_path: Path) -> list[dict]:
    raw_text = raw_path.read_text(encoding="utf-8")

    lines = raw_text.splitlines()
    source_url  = lines[0].replace("URL: ", "").strip()  if lines else ""
    source_slug = lines[1].replace("SLUG: ", "").strip() if len(lines) > 1 else ""
    sep_idx     = next((i for i, l in enumerate(lines) if l.startswith("="*10)), 2)
    body        = "\n".join(lines[sep_idx + 1:])

    title_starts = find_title_starts(body)
    if not title_starts:
        return []

    laudos = []
    for i, (start, title) in enumerate(title_starts):
        end = title_starts[i + 1][0] if i + 1 < len(title_starts) else len(body)
        content = body[start:end].strip()

        # Remove o título do início do conteúdo
        if content.startswith(title):
            content_body = content[len(title):].strip()
        else:
            content_body = content

        content_body = clean_content(content_body)

        if len(content_body) < 50:
            continue

        laudos.append({
            "title":       title,
            "source_url":  source_url,
            "source_slug": source_slug,
            "content":     content_body,
            "words":       len(content_body.split()),
        })

    return laudos


def save_laudo(laudo: dict, out_dir: Path) -> Path:
    slug   = title_to_slug(laudo["title"])
    prefix = laudo["source_slug"][:40].rstrip("_")
    fname  = f"{prefix}__{slug}.txt"
    path   = out_dir / fname

    if path.exists():
        base = path.stem
        n = 2
        while (out_dir / f"{base}_{n}.txt").exists():
            n += 1
        path = out_dir / f"{base}_{n}.txt"

    path.write_text(
        f"TITLE: {laudo['title']}\n"
        f"URL: {laudo['source_url']}\n"
        f"SOURCE_SLUG: {laudo['source_slug']}\n"
        f"{'=' * 60}\n"
        f"{laudo['content']}\n",
        encoding="utf-8",
    )
    return path


def main():
    # Limpa saída anterior
    for f in OUT_DIR.glob("*.txt"):
        f.unlink()

    raw_files = sorted(RAW_DIR.glob("*.txt"))
    print(f"Arquivos raw: {len(raw_files)}")

    index   = []
    total   = 0
    skipped = 0

    for raw_path in raw_files:
        laudos = split_file(raw_path)
        if not laudos:
            skipped += 1
            continue

        for laudo in laudos:
            out_path = save_laudo(laudo, OUT_DIR)
            total += 1
            index.append({
                "title":       laudo["title"],
                "source_url":  laudo["source_url"],
                "source_slug": laudo["source_slug"],
                "file":        str(out_path.relative_to(Path(__file__).parent)),
                "words":       laudo["words"],
            })

        print(f"  [{len(laudos):3} laudos] {raw_path.name[:70]}")

    IDX_FILE.write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    total_words = sum(e["words"] for e in index)
    print(f"\n=== Concluído ===")
    print(f"Raw processados  : {len(raw_files) - skipped} / {len(raw_files)}")
    print(f"Sem laudos       : {skipped}")
    print(f"Laudos gerados   : {total}")
    print(f"Total palavras   : {total_words:,}")
    print(f"Índice           : {IDX_FILE}")


if __name__ == "__main__":
    main()
