"""
Gerador de laudos médicos sintéticos — Claude Haiku + Admin Pipeline.

Gera ~100 laudos cobrindo as principais modalidades diagnósticas e
os indexa diretamente no Qdrant via endpoint admin do backend.

Uso:
    pip install anthropic httpx
    ANTHROPIC_API_KEY=<chave> ADMIN_API_KEY=<chave> python gerar_laudos_sinteticos.py

Variáveis de ambiente opcionais:
    BACKEND_URL   (padrão: produção Azure)
    HAIKU_MODEL   (padrão: claude-haiku-4-5-20251001)
"""

import os
import sys
import time
import json
from pathlib import Path

import anthropic
import httpx

# ── Configuração ──────────────────────────────────────────────────────────────

BACKEND_URL   = os.getenv("BACKEND_URL", "https://laudifier-production-backend.wonderfulsand-193c30c5.brazilsouth.azurecontainerapps.io")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
HAIKU_MODEL   = os.getenv("HAIKU_MODEL", "claude-haiku-4-5-20251001")

ENDPOINT    = f"{BACKEND_URL}/admin/pipeline/indexar"
OUTPUT_DIR  = Path(__file__).parent / "data" / "laudos" / "sinteticos"
TIMEOUT     = 300
MAX_RETRIES = 3

# ── Catálogo de exames ────────────────────────────────────────────────────────
# Cada entrada: (especialidade, tipo_laudo, variantes)
# Variantes: lista de cenários clínicos para gerar laudos distintos

EXAMES = [
    # ── Tomografia ──────────────────────────────────────────────────────────
    ("radiologia", "TC_abdome_superior_figado", [
        "exame normal, fígado homogêneo sem lesões focais",
        "esteatose hepática moderada, sem outras alterações",
        "cisto hepático simples no segmento VI, 2,5 cm",
        "hemangioma hepático típico no segmento VII",
    ]),
    ("radiologia", "TC_abdome_pâncreas", [
        "pâncreas de aspecto normal",
        "pancreatite aguda edematosa leve, sem necrose",
        "cisto pancreático simples no corpo, 1,8 cm",
    ]),
    ("radiologia", "TC_abdome_rins_vias_urinarias", [
        "rins de aspecto normal, sem litíase",
        "urolitíase no ureter distal direito, 6 mm",
        "cisto renal simples bilateral (Bosniak I)",
    ]),
    ("radiologia", "TC_torax", [
        "pulmões sem alterações, sem derrame pleural",
        "nódulo pulmonar solitário de 8 mm no lobo superior direito",
        "derrame pleural bilateral pequeno, consolidação em base direita",
        "enfisema pulmonar difuso, sem lesões focais",
    ]),
    ("radiologia", "TC_cranio_encefalo", [
        "exame normal, sem lesões intracranianas",
        "infarto isquêmico agudo no território da ACM esquerda",
        "hemorragia subaracnóidea de pequeno volume",
        "metástase única no lobo parietal direito, 1,5 cm",
    ]),
    ("radiologia", "TC_coluna_lombar", [
        "coluna lombar sem alterações significativas",
        "protrusão discal L4-L5 com compressão radicular",
        "hérnia de disco extrusa L5-S1 com compressão do saco dural",
        "espondilólise bilateral em L5",
    ]),
    ("radiologia", "TC_pelve", [
        "pelve feminina sem alterações",
        "tumor ovariano bilateral sugestivo de cistoadenoma seroso",
        "espessamento endometrial de 14 mm",
    ]),
    # ── Ressonância Magnética ───────────────────────────────────────────────
    ("radiologia", "RM_encefalo", [
        "encéfalo sem alterações de sinal ou morfologia",
        "lesões desmielinizantes periventriculares sugestivas de esclerose múltipla",
        "glioma de baixo grau no lobo frontal esquerdo, 3 cm",
        "acidente vascular cerebral isquêmico subagudo em território da ACM",
    ]),
    ("radiologia", "RM_coluna_cervical", [
        "coluna cervical sem alterações",
        "protrusão discal C5-C6 com mielopatia leve",
        "hérnia discal C6-C7 com radiculopatia",
    ]),
    ("radiologia", "RM_coluna_lombar", [
        "coluna lombar sem sinais de compressão radicular",
        "estenose do canal em L3-L4, moderada",
        "hérnia extrusa L4-L5 com sequestro",
    ]),
    ("radiologia", "RM_joelho", [
        "joelho direito sem lesões ligamentares ou meniscais",
        "ruptura do menisco medial, corno posterior",
        "lesão do ligamento cruzado anterior — ruptura completa",
        "condromalácia patelar grau III",
    ]),
    ("radiologia", "RM_abdome_figado", [
        "fígado de sinal homogêneo, sem lesões focais",
        "hemangioma típico segmento VI, 3,2 cm, com realce centrífugo",
        "lesão focal indeterminada no segmento IV, necessita correlação",
    ]),
    ("radiologia", "RM_mama", [
        "mamas sem lesões suspeitas bilateralmente",
        "nódulo espiculado na mama direita, quadrante superolateral — BIRADS 5",
        "realce assimétrico na mama esquerda — BIRADS 3, seguimento recomendado",
    ]),
    # ── Radiografia ────────────────────────────────────────────────────────
    ("radiologia", "RX_torax", [
        "radiografia de tórax sem alterações",
        "cardiomegalia grau II, congestão pulmonar",
        "consolidação pneumônica em lobo inferior direito",
        "derrame pleural esquerdo de médio volume",
        "pneumotórax direito espontâneo",
    ]),
    ("radiologia", "RX_coluna_lombar", [
        "coluna lombar sem alterações",
        "redução do espaço discal L4-L5 com osteofitose",
        "escoliose lombar de 18 graus, Cobb",
    ]),
    ("radiologia", "RX_mao_punho", [
        "mão e punho sem fraturas ou luxações",
        "fratura do escafóide — traço linear na cintura",
        "osteoartrose carpometacárpica bilateral",
    ]),
    # ── Ultrassonografia ───────────────────────────────────────────────────
    ("radiologia", "US_abdome_total", [
        "abdome superior e inferior sem alterações ecográficas",
        "colecistolitíase — múltiplos cálculos, vesícula com paredes normais",
        "esplenomegalia leve (14 cm), sem lesões focais esplênicas",
        "hepatomegalia difusa com ecotextura heterogênea, sugestiva de hepatopatia crônica",
    ]),
    ("radiologia", "US_pelvica_feminina", [
        "útero e anexos sem alterações",
        "mioma uterino intramural de 3,5 cm",
        "cisto simples no ovário direito, 4 cm",
        "endometrioma no ovário esquerdo, 3,8 cm",
    ]),
    ("radiologia", "US_tireoide", [
        "tireoide com volume e ecotextura normais, sem nódulos",
        "nódulo sólido hipoecogênico no lobo direito, 1,2 cm — TI-RADS 4",
        "bócio multinodular difuso bilateral",
    ]),
    ("radiologia", "US_obstetrica", [
        "gestação tópica de 20 semanas, morfologia fetal normal",
        "gestação de 12 semanas com translucência nucal aumentada (3,5 mm)",
        "placenta prévia total em gestação de 28 semanas",
    ]),
    ("radiologia", "US_doppler_membros_inferiores", [
        "sistema venoso profundo sem trombose",
        "trombose venosa profunda em veia poplítea direita",
        "insuficiência venosa superficial bilateral, varizes safena magna",
    ]),
    # ── Mamografia ─────────────────────────────────────────────────────────
    ("radiologia", "Mamografia", [
        "mamas sem alterações, BIRADS 1",
        "calcificações difusas benignas bilaterais, BIRADS 2",
        "nódulo denso espiculado na mama direita — BIRADS 5",
        "assimetria focal na mama esquerda — BIRADS 0, complementar com US",
    ]),
    # ── Cardiologia ────────────────────────────────────────────────────────
    ("cardiologia", "Ecocardiograma_transtorácico", [
        "ecocardiograma dentro dos limites da normalidade",
        "disfunção diastólica grau I, hipertrofia ventricular esquerda leve",
        "insuficiência mitral moderada, fração de ejeção preservada (64%)",
        "estenose aórtica grave — gradiente médio 45 mmHg, área valvar 0,8 cm²",
    ]),
    ("cardiologia", "Teste_ergoespirometrico", [
        "teste ergométrico negativo para isquemia miocárdica",
        "teste ergométrico positivo — infradesnivelamento 2 mm em V5 no pico do esforço",
        "teste interrompido por fadiga muscular, sem alterações isquêmicas",
    ]),
    # ── Medicina Nuclear ───────────────────────────────────────────────────
    ("medicina_nuclear", "Cintilografia_ossea", [
        "cintilografia óssea sem focos de hipercaptação patológica",
        "múltiplos focos de hipercaptação — compatíveis com metástases ósseas",
        "hipercaptação focal em L3 — fratura por compressão, sem outras lesões",
    ]),
    ("medicina_nuclear", "PET_CT_oncologico", [
        "PET-CT sem evidência de doença metabólica ativa",
        "lesão hipermetabólica no lobo inferior direito — SUVmax 8,4, sugestiva de neoplasia primária",
        "múltiplas lesões hipermetabólicas hepáticas — metástases, sem outros focos",
    ]),
    # ── Patologia ──────────────────────────────────────────────────────────
    ("patologia", "Biopsia_hepatica", [
        "biópsia hepática — hepatite crônica por VHC, fibrose grau F2 (METAVIR)",
        "biópsia hepática — esteatohepatite não alcoólica (NASH), fibrose F1",
        "biópsia hepática — cirrose hepática, sem displasia",
    ]),
    ("patologia", "Biopsia_mama", [
        "biópsia de mama — fibroadenoma com características típicas",
        "biópsia de mama — carcinoma ductal invasivo grau II, receptores hormonais positivos",
        "biópsia de mama — carcinoma lobular in situ (CLIS)",
    ]),
    ("patologia", "Biopsia_prostata", [
        "biópsia de próstata — sem evidência de malignidade (12 fragmentos)",
        "biópsia de próstata — adenocarcinoma Gleason 3+4=7 em 4/12 fragmentos",
        "biópsia de próstata — adenocarcinoma Gleason 4+5=9, alto grau",
    ]),
    ("patologia", "Biopsia_colo_uterino", [
        "biópsia de colo uterino — NIC I (displasia leve)",
        "biópsia de colo uterino — NIC III (displasia grave / carcinoma in situ)",
        "biópsia de colo uterino — carcinoma espinocelular invasivo",
    ]),
    # ── Endoscopia ─────────────────────────────────────────────────────────
    ("gastroenterologia", "Endoscopia_digestiva_alta", [
        "EDA sem alterações — esôfago, estômago e duodeno normais",
        "gastrite crônica antral com teste de urease positivo para H. pylori",
        "úlcera gástrica em pequena curvatura, A2 (Sakita), sem sinais de sangramento",
        "esôfago de Barrett — segmento curto 2 cm, biópsia sem displasia",
    ]),
    ("gastroenterologia", "Colonoscopia", [
        "colonoscopia até o ceco — mucosa cólica sem alterações",
        "pólipo tubular no cólon sigmoide, 8 mm, ressecado com pinça",
        "colite ulcerativa em atividade moderada — pancolite",
        "adenocarcinoma no cólon ascendente, lesão circunferencial, biópsia positiva",
    ]),
]

# ── Prompt de geração ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Você é um médico especialista que redige laudos médicos em português brasileiro.
Gere laudos completos, clinicamente precisos, em formato estruturado.
Use terminologia técnica médica correta. Seja detalhado e realista."""

def _prompt_laudo(especialidade: str, tipo: str, cenario: str) -> str:
    return f"""Gere um laudo médico completo e realista para:

Especialidade: {especialidade.replace('_', ' ').title()}
Tipo de exame: {tipo.replace('_', ' ')}
Cenário clínico: {cenario}

O laudo deve conter:
1. Cabeçalho com identificação do exame (campos em [COLCHETES] para dados do paciente)
2. Técnica utilizada
3. Achados / Descrição detalhada
4. Impressão diagnóstica
5. Conclusão e recomendações
6. Campo de assinatura

Seja clinicamente preciso e use terminologia médica adequada."""


# ── Geração ───────────────────────────────────────────────────────────────────

def gerar_laudo(client: anthropic.Anthropic, especialidade: str, tipo: str, cenario: str) -> str:
    msg = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _prompt_laudo(especialidade, tipo, cenario)}],
    )
    return msg.content[0].text


# ── Indexação ─────────────────────────────────────────────────────────────────

def indexar_arquivo(http: httpx.Client, path: Path, especialidade: str, tipo: str) -> dict:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with open(path, "rb") as f:
                r = http.post(
                    ENDPOINT,
                    files=[("files", (path.name, f.read(), "text/plain"))],
                    data={"source": "sintetico", "especialidade": especialidade, "tipo_laudo": tipo},
                    headers={"x-admin-key": ADMIN_API_KEY},
                    timeout=TIMEOUT,
                )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt < MAX_RETRIES:
                print(f"      ↩️  Tentativa {attempt}/{MAX_RETRIES}: {str(e)[:80]} — aguardando 5s...")
                time.sleep(5)
            else:
                raise


# ── Principal ─────────────────────────────────────────────────────────────────

def main():
    if not ANTHROPIC_KEY:
        print("❌ ANTHROPIC_API_KEY não definida.")
        sys.exit(1)
    if not ADMIN_API_KEY:
        print("❌ ADMIN_API_KEY não definida.")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"📁 Saída: {OUTPUT_DIR}")

    total_exames    = sum(len(v) for _, _, v in EXAMES)
    print(f"📋 {len(EXAMES)} tipos de exame × variantes = {total_exames} laudos a gerar")
    print(f"🤖 Modelo: {HAIKU_MODEL}")
    print(f"🔌 Backend: {BACKEND_URL}\n")

    anthr   = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    total_gerados   = 0
    total_indexados = 0
    total_chunks    = 0
    erros           = []

    with httpx.Client() as http:
        for especialidade, tipo, variantes in EXAMES:
            print(f"📂 {tipo.replace('_', ' ')} [{especialidade}]")

            for i, cenario in enumerate(variantes, 1):
                slug      = f"{tipo}_{i:02d}"
                filepath  = OUTPUT_DIR / f"{slug}.txt"

                # Gera laudo
                try:
                    print(f"  [{i}/{len(variantes)}] Gerando: {cenario[:60]}...")
                    laudo = gerar_laudo(anthr, especialidade, tipo, cenario)
                    # Prefixo para o chunker do pipeline identificar metadados
                    header = (
                        f"=== {tipo.replace('_', ' ')} — Variante {i} ===\n"
                        f"Especialidade: {especialidade}\n"
                        f"Cenário: {cenario}\n"
                        f"Fonte: sintético — gerado por Claude\n\n"
                    )
                    filepath.write_text(header + laudo, encoding="utf-8")
                    total_gerados += 1
                except Exception as e:
                    print(f"  ❌ Falha na geração: {e}")
                    erros.append({"fase": "geracao", "arquivo": slug, "erro": str(e)})
                    continue

                # Indexa
                try:
                    res = indexar_arquivo(http, filepath, especialidade, tipo.replace("_", " "))
                    chunks = res.get("chunks_indexed", 0)
                    total_indexados += 1
                    total_chunks    += chunks
                    print(f"  ✅ Indexado: {chunks} chunks")
                except Exception as e:
                    print(f"  ❌ Falha na indexação: {e}")
                    erros.append({"fase": "indexacao", "arquivo": slug, "erro": str(e)})

                time.sleep(0.3)  # rate limit gentil

            print()

    # Relatório
    print("=" * 60)
    print(f"✅ Laudos gerados:   {total_gerados}/{total_exames}")
    print(f"✅ Laudos indexados: {total_indexados}/{total_gerados}")
    print(f"✅ Chunks no Qdrant: {total_chunks}")
    print(f"❌ Erros:            {len(erros)}")
    if erros:
        print("\nErros detalhados:")
        for e in erros:
            print(f"  {e['fase']} | {e['arquivo']}: {e['erro'][:100]}")

    # Salva relatório
    report = {
        "total_gerados": total_gerados,
        "total_indexados": total_indexados,
        "total_chunks": total_chunks,
        "erros": erros,
    }
    (Path(__file__).parent / "sinteticos_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)
    )
    print("\n📄 Relatório salvo em sinteticos_report.json")


if __name__ == "__main__":
    main()
