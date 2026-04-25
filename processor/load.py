"""Load: escreve templates.json, pairs.jsonl e chunks.jsonl."""
from __future__ import annotations

import json
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent / "data"
RAG_DIR       = _BASE / "rag"
FINETUNE_DIR  = _BASE / "finetune"
TEMPLATES_DIR = _BASE / "templates"

SYSTEM_PROMPT = (
    "Você é um assistente especializado em radiologia médica. "
    "Gere laudos radiológicos completos e precisos em português brasileiro, "
    "seguindo o padrão do Compêndio da Radiologia."
)


def ensure_dirs() -> None:
    for d in (RAG_DIR, FINETUNE_DIR, TEMPLATES_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Templates JSON
# ---------------------------------------------------------------------------

def build_templates(all_laudos: list[dict]) -> tuple[list[dict], dict[str, list[dict]]]:
    templates = [
        {
            "titulo":     l["titulo"],
            "modalidade": l["modalidade"],
            "regiao":     l["regiao"],
            "categoria":  l["categoria"],
            "tecnica":    l["tecnica"],
            "indicacao":  l["indicacao"],
            "analise":    l["analise"],
            "opiniao":    l["opiniao"],
            "source_url": l["source_url"],
            "words":      l["words"],
        }
        for l in all_laudos
    ]

    grouped: dict[str, list[dict]] = {}
    for t in templates:
        key = f"{t['modalidade']} / {t['regiao']}"
        grouped.setdefault(key, []).append(t)

    return templates, grouped


def write_templates(templates: list[dict], grouped: dict[str, list[dict]]) -> None:
    out = {
        "total": len(templates),
        "por_modalidade_regiao": {k: v for k, v in sorted(grouped.items())},
    }
    (TEMPLATES_DIR / "templates.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Fine-tuning JSONL
# ---------------------------------------------------------------------------

def build_finetune_pairs(all_laudos: list[dict], all_frases: list[dict]) -> list[dict]:
    records: list[dict] = []

    for l in all_laudos:
        if not l["tecnica"] and not l["analise"]:
            continue  # skip empty laudos

        # Pair 1: generate full laudo given title + indicação
        user_prompt = f"Gere um laudo de {l['titulo']}."
        if l["indicacao"]:
            user_prompt += f" Indicação: {l['indicacao']}"

        records.append({
            "messages": [
                {"role": "system",    "content": SYSTEM_PROMPT},
                {"role": "user",      "content": user_prompt},
                {"role": "assistant", "content": l["full_text"]},
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
            records.append({
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
        records.append({
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

    return records


def write_finetune_pairs(records: list[dict]) -> None:
    with open(FINETUNE_DIR / "pairs.jsonl", "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# RAG JSONL
# ---------------------------------------------------------------------------

def build_rag_chunks(all_laudos: list[dict], all_frases: list[dict]) -> list[dict]:
    records: list[dict] = []

    # Laudos → one chunk per laudo (full context)
    for l in all_laudos:
        records.append({
            "id":         f"laudo_{len(records)}",
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
        records.append({
            "id":         f"frase_{len(records)}",
            "text":       f["full_text"],
            "tipo":       "frase-diagnostica",
            "titulo":     f["heading"],
            "modalidade": f["modalidade"],
            "regiao":     f["regiao"],
            "source_url": f["source_url"],
            "words":      f["words"],
        })

    return records


def write_rag_chunks(records: list[dict]) -> None:
    with open(RAG_DIR / "chunks.jsonl", "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
