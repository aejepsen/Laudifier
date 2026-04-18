"""
Avaliação do modelo de geração de laudos — Laudifier.

Métricas calculadas:
  1. RAG Hit Rate       — % de queries com score >= threshold no Qdrant
  2. Completude         — média de campos faltando por laudo gerado
  3. LLM-as-Judge       — Claude avalia qualidade clínica (1–5) em amostra
  4. Latência           — tempo médio de geração (time-to-first-token + total)
  5. Tipo de geração    — % RAG vs fallback

Uso:
    ANTHROPIC_API_KEY=<chave> ADMIN_API_KEY=<chave> python avaliar_modelo.py

    # Apenas RAG (sem gerar laudos completos — mais rápido):
    ANTHROPIC_API_KEY=<chave> ADMIN_API_KEY=<chave> python avaliar_modelo.py --rag-only

    # Amostra reduzida (N queries aleatórias):
    python avaliar_modelo.py --sample 10
"""

import os
import sys
import json
import time
import re
import random
import argparse
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import httpx

# ── Configuração ──────────────────────────────────────────────────────────────

BACKEND_URL   = os.getenv("BACKEND_URL", "https://laudifier-production-backend.wonderfulsand-193c30c5.brazilsouth.azurecontainerapps.io")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
SUPABASE_TOKEN = os.getenv("EVAL_BEARER_TOKEN", "")  # token de usuário de teste

RAG_THRESHOLD   = 0.60
JUDGE_MODEL     = "claude-haiku-4-5-20251001"   # avaliação — barato
GERAR_ENDPOINT  = f"{BACKEND_URL}/laudos/gerar"
STATUS_ENDPOINT = f"{BACKEND_URL}/admin/pipeline/status"

# ── Queries de avaliação ──────────────────────────────────────────────────────
# (query, especialidade, desc)
EVAL_QUERIES = [
    # Tomografia
    ("TC abdome superior com foco hepático, paciente 55 anos",          "radiologia",         "TC fígado"),
    ("tomografia de tórax com nódulo pulmonar",                          "radiologia",         "TC tórax nódulo"),
    ("TC crânio sem contraste, cefaleia intensa",                        "radiologia",         "TC crânio"),
    ("tomografia coluna lombar, dor radicular L5",                       "radiologia",         "TC coluna lombar"),
    ("TC de rins e vias urinárias, suspeita de cálculo",                 "radiologia",         "TC rins"),
    # RM
    ("ressonância magnética de encéfalo com contraste",                  "radiologia",         "RM encéfalo"),
    ("RM coluna cervical, mielopatia",                                   "radiologia",         "RM coluna cervical"),
    ("ressonância de joelho direito, suspeita de lesão meniscal",        "radiologia",         "RM joelho"),
    ("RM de mama bilateral com gadolínio",                               "radiologia",         "RM mama"),
    # RX
    ("radiografia de tórax PA e perfil",                                 "radiologia",         "RX tórax"),
    ("raio-x de coluna lombar",                                          "radiologia",         "RX coluna"),
    # US
    ("ultrassonografia de abdome total",                                 "radiologia",         "US abdome"),
    ("ultrassom pélvico feminino transvaginal",                          "radiologia",         "US pelve"),
    ("ultrassonografia de tireoide com doppler",                         "radiologia",         "US tireoide"),
    ("ultrassonografia obstétrica morfológica 20 semanas",               "radiologia",         "US obstétrica"),
    # Mamografia
    ("mamografia bilateral, rastreamento",                               "radiologia",         "Mamografia"),
    # Cardiologia
    ("ecocardiograma transtorácico com doppler",                         "cardiologia",        "Ecocardiograma"),
    ("teste ergométrico máximo",                                         "cardiologia",        "Teste ergométrico"),
    # Medicina Nuclear
    ("cintilografia óssea total com tecnécio",                           "medicina_nuclear",   "Cintilografia óssea"),
    ("PET-CT oncológico com FDG",                                        "medicina_nuclear",   "PET-CT"),
    # Patologia
    ("biópsia hepática percutânea",                                      "patologia",          "Biópsia fígado"),
    ("biópsia de mama guiada por ultrassom",                             "patologia",          "Biópsia mama"),
    ("biópsia de próstata transretal 12 fragmentos",                     "patologia",          "Biópsia próstata"),
    # Endoscopia
    ("endoscopia digestiva alta com biópsia gástrica",                   "gastroenterologia",  "EDA"),
    ("colonoscopia total com polipectomia",                              "gastroenterologia",  "Colonoscopia"),
]

# ── Rubrica do juiz ───────────────────────────────────────────────────────────

JUDGE_SYSTEM = """Você é um médico avaliador experiente.
Avalie laudos médicos gerados por IA em 5 dimensões, atribuindo nota de 1 a 5 a cada uma.
Responda APENAS com JSON válido, sem texto extra."""

def _prompt_judge(query: str, especialidade: str, laudo: str) -> str:
    return f"""Avalie o laudo médico abaixo gerado por IA:

SOLICITAÇÃO: {query}
ESPECIALIDADE: {especialidade}

LAUDO GERADO:
{laudo[:3000]}

Responda com JSON:
{{
  "completude": <1-5>,          // todos os campos obrigatórios presentes?
  "precisao_clinica": <1-5>,    // terminologia e achados clinicamente corretos?
  "estrutura": <1-5>,           // organização e formatação adequadas?
  "utilidade_clinica": <1-5>,   // um médico consegue usar este laudo?
  "geral": <1-5>,               // avaliação geral
  "comentario": "<1 frase>"
}}"""


# ── RAG Hit Rate via Qdrant direto ────────────────────────────────────────────

def _check_rag_qdrant(query: str, top_k: int = 5) -> float:
    """Embute query localmente e busca no Qdrant. Retorna score máximo."""
    try:
        from sentence_transformers import SentenceTransformer
        from qdrant_client import QdrantClient

        qdrant_url = os.getenv("QDRANT_URL", "")
        qdrant_key = os.getenv("QDRANT_API_KEY", "")
        collection = os.getenv("QDRANT_COLLECTION", "laudos_medicos")

        if not qdrant_url:
            return -1.0  # Qdrant não configurado localmente

        device = os.getenv("EVAL_DEVICE", "cpu")  # GPU disponível: EVAL_DEVICE=cuda
        model  = SentenceTransformer("intfloat/multilingual-e5-large", device=device)
        vec    = model.encode(f"query: {query}", normalize_embeddings=True).tolist()
        client = QdrantClient(url=qdrant_url, api_key=qdrant_key or None)
        hits   = client.search(collection_name=collection, query_vector=vec, limit=top_k)
        return max((h.score for h in hits), default=0.0)
    except ImportError:
        return -1.0  # dependências não instaladas localmente


# ── Geração com SSE ──────────────────────────────────────────────────────────

def _gerar_laudo_sse(http: httpx.Client, query: str, especialidade: str) -> dict:
    """
    Chama /laudos/gerar via SSE e coleta: laudo, tipo_geracao, score, campos_faltando, latência.
    Requer EVAL_BEARER_TOKEN.
    """
    if not SUPABASE_TOKEN:
        return {"erro": "EVAL_BEARER_TOKEN não definido"}

    t0     = time.time()
    result = {
        "laudo": "",
        "tipo_geracao": "",
        "score": 0.0,
        "campos_faltando": [],
        "tem_memoria": False,
        "ttfb": 0.0,       # time-to-first-byte
        "total_s": 0.0,
        "erro": None,
    }

    try:
        with http.stream(
            "POST", GERAR_ENDPOINT,
            json={"solicitacao": query, "especialidade": especialidade, "dados_clinicos": {}},
            headers={
                "Authorization": f"Bearer {SUPABASE_TOKEN}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            timeout=120,
        ) as resp:
            first_byte = True
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                if first_byte:
                    result["ttfb"] = round(time.time() - t0, 2)
                    first_byte = False
                try:
                    chunk = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue

                t = chunk.get("type", "")
                if t == "meta":
                    result["score"]       = chunk.get("score", 0.0)
                    result["tipo_geracao"] = chunk.get("tipo_geracao", "")
                    result["tem_memoria"] = chunk.get("tem_memoria", False)
                elif t == "token":
                    result["laudo"] += chunk.get("text", "")
                elif t == "done":
                    result["campos_faltando"] = chunk.get("campos_faltando", [])
                    break
                elif t == "error":
                    result["erro"] = chunk.get("error", "unknown error")
                    break

    except Exception as e:
        result["erro"] = str(e)

    result["total_s"] = round(time.time() - t0, 2)
    return result


# ── Juiz ─────────────────────────────────────────────────────────────────────

def _avaliar_laudo(anthr: anthropic.Anthropic, query: str, especialidade: str, laudo: str) -> dict:
    if not laudo.strip():
        return {"erro": "laudo vazio"}
    try:
        msg  = anthr.messages.create(
            model=JUDGE_MODEL,
            max_tokens=300,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": _prompt_judge(query, especialidade, laudo)}],
        )
        raw  = msg.content[0].text.strip()
        # Extrai JSON mesmo com texto extra
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            return json.loads(m.group())
        return {"erro": f"JSON inválido: {raw[:100]}"}
    except Exception as e:
        return {"erro": str(e)}


# ── Principal ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rag-only", action="store_true", help="Apenas RAG hit rate (sem gerar laudos)")
    parser.add_argument("--sample",   type=int, default=0,  help="Avaliar N queries aleatórias")
    args = parser.parse_args()

    if not ANTHROPIC_KEY:
        print("❌ ANTHROPIC_API_KEY não definida.")
        sys.exit(1)

    queries = list(EVAL_QUERIES)
    if args.sample > 0:
        queries = random.sample(queries, min(args.sample, len(queries)))

    print(f"🔬 Laudifier — Avaliação do Modelo")
    print(f"📊 {len(queries)} queries | RAG-only: {args.rag_only}")
    print(f"🔌 Backend: {BACKEND_URL}\n")

    anthr   = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    results = []

    # ── Status do Qdrant ──────────────────────────────────────────────────────
    qdrant_points = 0
    if ADMIN_API_KEY:
        try:
            with httpx.Client() as http:
                r = http.get(STATUS_ENDPOINT, headers={"x-admin-key": ADMIN_API_KEY}, timeout=30)
                qdrant_points = r.json().get("points", 0)
                print(f"📦 Qdrant: {qdrant_points} pontos na coleção\n")
        except Exception as e:
            print(f"⚠️  Qdrant status indisponível: {e}\n")

    with httpx.Client() as http:
        for i, (query, especialidade, desc) in enumerate(queries, 1):
            print(f"[{i:02d}/{len(queries):02d}] {desc}")
            row = {"query": query, "especialidade": especialidade, "desc": desc}

            # ── RAG score (via Qdrant local se disponível) ────────────────────
            score_local = _check_rag_qdrant(query)
            if score_local >= 0:
                row["rag_score_local"] = round(score_local, 3)
                row["rag_hit_local"]   = score_local >= RAG_THRESHOLD
                print(f"  RAG local:  score={score_local:.3f} → {'✅ HIT' if row['rag_hit_local'] else '❌ MISS'}")

            if args.rag_only:
                results.append(row)
                continue

            # ── Geração via SSE ───────────────────────────────────────────────
            if not SUPABASE_TOKEN:
                print("  ⚠️  EVAL_BEARER_TOKEN ausente — pulando geração")
                results.append(row)
                continue

            gen = _gerar_laudo_sse(http, query, especialidade)
            row.update({
                "rag_score_api":  round(gen.get("score", 0.0), 3),
                "rag_hit_api":    gen.get("score", 0.0) >= RAG_THRESHOLD,
                "tipo_geracao":   gen.get("tipo_geracao", ""),
                "campos_faltando_n": len(gen.get("campos_faltando", [])),
                "campos_faltando":   gen.get("campos_faltando", []),
                "ttfb_s":         gen.get("ttfb", 0.0),
                "total_s":        gen.get("total_s", 0.0),
                "tem_memoria":    gen.get("tem_memoria", False),
                "erro_api":       gen.get("erro"),
            })

            if gen.get("erro"):
                print(f"  ❌ API: {gen['erro']}")
            else:
                print(f"  API:  tipo={gen['tipo_geracao']} | score={row['rag_score_api']:.3f} | "
                      f"campos={row['campos_faltando_n']} | ttfb={row['ttfb_s']}s | total={row['total_s']}s")

                # ── LLM-as-Judge ─────────────────────────────────────────────
                laudo = gen.get("laudo", "")
                if laudo:
                    print(f"  Avaliando qualidade com {JUDGE_MODEL}...")
                    scores = _avaliar_laudo(anthr, query, especialidade, laudo)
                    row["judge"] = scores
                    if "erro" not in scores:
                        geral = scores.get("geral", "?")
                        print(f"  Qualidade: geral={geral}/5 | {scores.get('comentario','')[:80]}")
                    else:
                        print(f"  ⚠️  Judge: {scores['erro']}")

            results.append(row)
            time.sleep(1)  # rate limit

    # ── Métricas agregadas ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("📊 MÉTRICAS AGREGADAS")
    print("=" * 60)

    # RAG Hit Rate
    rag_hits_api   = [r for r in results if r.get("rag_hit_api") is True]
    rag_hits_local = [r for r in results if r.get("rag_hit_local") is True]
    rag_api_total  = [r for r in results if "rag_hit_api" in r]
    rag_loc_total  = [r for r in results if "rag_hit_local" in r]

    if rag_api_total:
        hit_rate = len(rag_hits_api) / len(rag_api_total) * 100
        print(f"RAG Hit Rate (API):   {hit_rate:.1f}%  ({len(rag_hits_api)}/{len(rag_api_total)})")
    if rag_loc_total:
        hit_rate_l = len(rag_hits_local) / len(rag_loc_total) * 100
        print(f"RAG Hit Rate (local): {hit_rate_l:.1f}%  ({len(rag_hits_local)}/{len(rag_loc_total)})")

    # Tipo de geração
    tipos = [r.get("tipo_geracao") for r in results if r.get("tipo_geracao")]
    if tipos:
        rag_pct = tipos.count("rag") / len(tipos) * 100
        print(f"Tipo geração:         {rag_pct:.1f}% RAG | {100-rag_pct:.1f}% fallback")

    # Completude
    campos = [r.get("campos_faltando_n", 0) for r in results if "campos_faltando_n" in r]
    if campos:
        print(f"Campos faltando:      média={sum(campos)/len(campos):.1f} | max={max(campos)} | min={min(campos)}")

    # Latência
    ttfbs  = [r["ttfb_s"]  for r in results if r.get("ttfb_s")]
    totals = [r["total_s"] for r in results if r.get("total_s")]
    if ttfbs:
        print(f"TTFB médio:           {sum(ttfbs)/len(ttfbs):.1f}s")
    if totals:
        print(f"Latência total média: {sum(totals)/len(totals):.1f}s")

    # LLM-as-Judge
    judge_scores = [r["judge"]["geral"] for r in results if isinstance(r.get("judge"), dict) and "geral" in r.get("judge", {})]
    if judge_scores:
        print(f"Qualidade média (1-5): {sum(judge_scores)/len(judge_scores):.2f}")

    # Erros
    erros = [r for r in results if r.get("erro_api")]
    print(f"Erros de API:         {len(erros)}")

    # ── Salva relatório ───────────────────────────────────────────────────────
    report = {
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "backend_url":    BACKEND_URL,
        "qdrant_points":  qdrant_points,
        "total_queries":  len(queries),
        "rag_threshold":  RAG_THRESHOLD,
        "resultados":     results,
        "agregado": {
            "rag_hit_rate_api":   len(rag_hits_api)   / max(len(rag_api_total), 1),
            "rag_hit_rate_local": len(rag_hits_local) / max(len(rag_loc_total), 1),
            "campos_faltando_media": sum(campos) / max(len(campos), 1),
            "ttfb_media_s":       sum(ttfbs) / max(len(ttfbs), 1),
            "total_s_media":      sum(totals) / max(len(totals), 1),
            "judge_geral_media":  sum(judge_scores) / max(len(judge_scores), 1),
            "erros_count":        len(erros),
        },
    }

    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = Path(__file__).parent / f"avaliacao_{ts}.json"
    outfile.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n📄 Relatório completo: {outfile.name}")

    # Markdown resumo
    md_lines = [
        f"# Avaliação Laudifier — {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        f"\n**Qdrant:** {qdrant_points} pontos | **Queries:** {len(queries)} | **Threshold RAG:** {RAG_THRESHOLD}",
        "\n## Métricas",
        f"| Métrica | Valor |",
        f"|---|---|",
    ]
    ag = report["agregado"]
    if rag_api_total:
        md_lines.append(f"| RAG Hit Rate (API) | {ag['rag_hit_rate_api']*100:.1f}% |")
    if rag_loc_total:
        md_lines.append(f"| RAG Hit Rate (local) | {ag['rag_hit_rate_local']*100:.1f}% |")
    if campos:
        md_lines.append(f"| Campos faltando (média) | {ag['campos_faltando_media']:.1f} |")
    if ttfbs:
        md_lines.append(f"| TTFB médio | {ag['ttfb_media_s']:.1f}s |")
    if totals:
        md_lines.append(f"| Latência total média | {ag['total_s_media']:.1f}s |")
    if judge_scores:
        md_lines.append(f"| Qualidade média (1-5) | {ag['judge_geral_media']:.2f} |")
    md_lines.append(f"| Erros | {ag['erros_count']} |")

    md_lines += [
        "\n## Detalhes por query",
        "| # | Exame | Tipo | Score | Campos | Qualidade | Latência |",
        "|---|---|---|---|---|---|---|",
    ]
    for j, r in enumerate(results, 1):
        score   = r.get("rag_score_api", r.get("rag_score_local", "—"))
        score_s = f"{score:.3f}" if isinstance(score, float) else str(score)
        campos_n = r.get("campos_faltando_n", "—")
        qual    = r.get("judge", {}).get("geral", "—") if isinstance(r.get("judge"), dict) else "—"
        lat     = f"{r.get('total_s', '—')}s"
        tipo    = r.get("tipo_geracao", "—")
        md_lines.append(f"| {j} | {r['desc']} | {tipo} | {score_s} | {campos_n} | {qual}/5 | {lat} |")

    md_file = outfile.with_suffix(".md")
    md_file.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"📄 Resumo Markdown:   {md_file.name}")


if __name__ == "__main__":
    main()
