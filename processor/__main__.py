"""Orquestrador ETL: extract → transform → load.

Uso: `python -m processor` na raiz do repo.
"""
from __future__ import annotations

from .extract import RAW_DIR, extract_metadata, load_raw
from .load import (
    FINETUNE_DIR,
    RAG_DIR,
    TEMPLATES_DIR,
    build_finetune_pairs,
    build_rag_chunks,
    build_templates,
    ensure_dirs,
    write_finetune_pairs,
    write_rag_chunks,
    write_templates,
)
from .transform import parse_frases, split_into_laudos


def _parse_file(path) -> tuple[list[dict], list[dict]]:
    """Processa 1 arquivo, retorna (laudos, frases) extraídos."""
    source_url, source_slug, body = load_raw(path)
    meta = extract_metadata(source_slug)
    meta["source_url"]  = source_url
    meta["source_slug"] = source_slug

    laudos: list[dict] = []
    frases: list[dict] = []

    if meta["categoria"] in ("modelo-laudo", "doppler"):
        laudos = split_into_laudos(body, meta)
        if laudos:
            print(f"  [laudo {len(laudos):3}] {path.name[:65]}")
            return laudos, frases

    if meta["categoria"] == "frases":
        frases = parse_frases(body, meta, source_url, source_slug)
        if frases:
            print(f"  [frase {len(frases):3}] {path.name[:65]}")
            return laudos, frases

    # Fallback: treat whole page as one chunk (protocols, reference, US models, etc.)
    laudos = split_into_laudos(body, meta)
    if laudos:
        print(f"  [misc  {len(laudos):3}] {path.name[:65]}")
    return laudos, frases


def _print_summary(
    templates: list[dict],
    grouped: dict[str, list[dict]],
    finetune_records: list[dict],
    rag_records: list[dict],
) -> None:
    ft_words  = sum(len(r["messages"][-1]["content"].split()) for r in finetune_records)
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


def main() -> None:
    ensure_dirs()

    raw_files = sorted(RAW_DIR.glob("*.txt"))
    print(f"Arquivos raw: {len(raw_files)}")

    all_laudos: list[dict] = []
    all_frases: list[dict] = []
    for path in raw_files:
        laudos, frases = _parse_file(path)
        all_laudos.extend(laudos)
        all_frases.extend(frases)

    print(f"\nLaudos: {len(all_laudos)}  |  Frases: {len(all_frases)}")

    templates, grouped = build_templates(all_laudos)
    write_templates(templates, grouped)

    finetune_records = build_finetune_pairs(all_laudos, all_frases)
    write_finetune_pairs(finetune_records)

    rag_records = build_rag_chunks(all_laudos, all_frases)
    write_rag_chunks(rag_records)

    _print_summary(templates, grouped, finetune_records, rag_records)


if __name__ == "__main__":
    main()
