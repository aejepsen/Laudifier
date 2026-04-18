"""
Gera laudos sintéticos COMPLETOS com valores reais preenchidos (não templates).
Usa Claude para criar laudos com achados específicos, medidas e impressão diagnóstica.

Uso: python gerar_sinteticos_completos.py
"""
import os, time, anthropic
from pathlib import Path

API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
OUTPUT_DIR = Path(__file__).parent / "data/laudos/sinteticos_completos"
MODEL     = "claude-haiku-4-5-20251001"  # rápido e barato para geração em massa

LAUDOS = [
    # (tipo_exame, variante, achado_principal)
    ("TC",  "cranio_normal",              "Tomografia computadorizada do crânio sem achados patológicos"),
    ("TC",  "cranio_avc_isquemico",       "Tomografia do crânio com hipodensidade frontal esquerda compatível com AVC isquêmico agudo"),
    ("TC",  "torax_nodulo_pulmonar",      "Tomografia do tórax com nódulo pulmonar sólido no lobo superior direito de 8mm"),
    ("TC",  "torax_normal",               "Tomografia de tórax sem alterações pleuroparenquimatosas significativas"),
    ("TC",  "abdome_figado_esteatose",    "Tomografia de abdome com esteatose hepática difusa moderada"),
    ("TC",  "abdome_colecistite",         "Tomografia de abdome com sinais de colecistite aguda calculosa"),
    ("TC",  "coluna_lombar_hernia",       "Tomografia da coluna lombar com hérnia discal L4-L5 com compressão radicular"),
    ("TC",  "coluna_lombar_espondilose",  "Tomografia da coluna lombar com alterações degenerativas e osteofitose"),
    ("TC",  "pelve_feminina_cisto",       "Tomografia de pelve com cisto ovariano simples de 4,2cm à direita"),
    ("TC",  "rins_nefrolitiase",          "Tomografia de rins e vias urinárias com cálculo renal de 6mm no ureter distal direito"),
    ("RM",  "encefalo_normal",            "Ressonância magnética do encéfalo sem alterações do sinal ou estruturais"),
    ("RM",  "encefalo_tumor",             "Ressonância do encéfalo com lesão expansiva em lobo temporal direito com realce heterogêneo"),
    ("RM",  "encefalo_esclerose_multipla","Ressonância do encéfalo com múltiplas lesões desmielinizantes periventricular"),
    ("RM",  "coluna_cervical_hernia",     "Ressonância da coluna cervical com hérnia discal C5-C6 com mielopatia"),
    ("RM",  "coluna_cervical_normal",     "Ressonância da coluna cervical sem compressão medular ou radicular"),
    ("RM",  "coluna_lombar_hernia",       "Ressonância da coluna lombar com hérnia discal L5-S1 extrusa com compressão da raiz S1"),
    ("RM",  "joelho_lesao_menisco",       "Ressonância do joelho com rotura do menisco medial em alça de balde"),
    ("RM",  "joelho_lca",                 "Ressonância do joelho com rotura completa do ligamento cruzado anterior"),
    ("RM",  "mama_birads3",               "Ressonância das mamas com nódulo de contornos regulares BI-RADS 3"),
    ("RM",  "abdome_hemangioma",          "Ressonância do abdome com hemangioma hepático típico de 2,3cm no segmento VI"),
    ("US",  "abdome_total_normal",        "Ultrassonografia do abdome total sem alterações ecográficas"),
    ("US",  "abdome_esteatose",           "Ultrassonografia do abdome com esteatose hepática grau II"),
    ("US",  "pelve_feminina_mioma",       "Ultrassonografia pélvica com útero miomatoso, mioma intramural de 3,1cm"),
    ("US",  "pelve_feminina_normal",      "Ultrassonografia pélvica feminina sem alterações ecográficas"),
    ("US",  "obstetrica_2trim",           "Ultrassonografia obstétrica de segundo trimestre com feto em apresentação cefálica"),
    ("US",  "tireoide_nodulo",            "Ultrassonografia da tireoide com nódulo sólido hipoecoico de 1,2cm no lobo direito TI-RADS 3"),
    ("US",  "tireoide_normal",            "Ultrassonografia da tireoide com parênquima homogêneo sem nódulos"),
    ("US",  "doppler_carótida",           "Ultrassonografia com Doppler das artérias carótidas com placa aterosclerótica na bifurcação direita"),
    ("US",  "doppler_mmii_tvp",           "Ultrassonografia com Doppler venoso dos membros inferiores com trombose venosa profunda na veia femoral esquerda"),
    ("RX",  "torax_normal",              "Radiografia do tórax sem alterações pleuroparenquimatosas"),
    ("RX",  "torax_pneumonia",            "Radiografia do tórax com opacidade em lobo inferior direito compatível com pneumonia"),
    ("RX",  "coluna_lombar_fratura",      "Radiografia da coluna lombar com fratura por compressão em L1"),
    ("RX",  "coluna_lombar_normal",       "Radiografia da coluna lombar sem desvio do eixo ou alterações ósseas significativas"),
    ("RX",  "mao_fratura",                "Radiografia da mão com fratura do 5º metacarpo sem desvio"),
    ("Mamografia", "birads2",             "Mamografia bilateral com achados benignos BI-RADS 2"),
    ("Mamografia", "birads4a",            "Mamografia bilateral com nódulo espiculado no quadrante superoexterno esquerdo BI-RADS 4A"),
    ("PET_CT", "negativo",               "PET-CT de corpo inteiro sem foco hipermetabólico patológico"),
    ("PET_CT", "metastase",              "PET-CT com múltiplos focos hipermetabólicos em linfonodos mediastinais e hepáticos"),
    ("Ecocardiograma", "normal",          "Ecocardiograma transtorácico com função sistólica e diastólica preservadas"),
    ("Ecocardiograma", "insuficiencia",   "Ecocardiograma com disfunção sistólica do ventrículo esquerdo e fração de ejeção de 35%"),
    ("Colonoscopia", "normal",            "Colonoscopia total sem alterações da mucosa"),
    ("Colonoscopia", "polipo",            "Colonoscopia com pólipo séssil de 8mm no cólon sigmoide removido por polipectomia"),
    ("Endoscopia", "gastrite",            "Endoscopia digestiva alta com gastrite antral erosiva e H. pylori positivo"),
    ("Endoscopia", "normal",              "Endoscopia digestiva alta sem alterações macroscópicas"),
    ("Biopsia", "mama_carcinoma",         "Biópsia de mama com carcinoma ductal invasivo grau II"),
    ("Biopsia", "mama_benigno",           "Biópsia de mama com fibroadenoma com alterações fibrocísticas"),
    ("Biopsia", "prostata_adenocarcinoma","Biópsia de próstata com adenocarcinoma Gleason 7 (3+4) em 3 de 12 fragmentos"),
    ("Biopsia", "prostata_benigno",       "Biópsia de próstata com hiperplasia benigna sem atipias"),
    ("Cintilografia", "ossea_normal",     "Cintilografia óssea de corpo inteiro sem focos de hipercaptação patológica"),
    ("Cintilografia", "ossea_metastase",  "Cintilografia óssea com múltiplos focos de hipercaptação em coluna e arcos costais compatíveis com metástases"),
]

SYSTEM = """Você é um radiologista/especialista sênior gerando laudos médicos COMPLETOS e REAIS para um banco de dados de referência.
REGRAS ABSOLUTAS:
- Gere laudos com valores REAIS e ESPECÍFICOS (medidas em mm/cm, densidades em UH, índices, etc.)
- NUNCA use [CAMPO], [VALOR], [ACHADO] ou qualquer placeholder entre colchetes nas seções clínicas
- Use apenas [NOME DO PACIENTE], [DATA DO EXAME], [CRM] para identificação — esses serão preenchidos depois
- Termine SEMPRE com IMPRESSÃO DIAGNÓSTICA completa e objetiva
- Use terminologia radiológica precisa em Português Brasileiro
- O laudo deve ser utilizável clinicamente sem qualquer edição nas seções de achados"""


def gerar_laudo(client: anthropic.Anthropic, tipo: str, variante: str, descricao: str) -> str:
    prompt = (
        f"Gere um laudo médico COMPLETO de {tipo} — {variante.replace('_', ' ')}.\n"
        f"Cenário clínico: {descricao}\n\n"
        f"O laudo deve conter valores numéricos reais (ex: 'lesão hipodensa de 2,3cm em segmento VIII', "
        f"'densidade de 45 UH', 'FE de 62%', 'protrusão de 4mm', etc.).\n"
        f"Inclua todas as seções padrão para este tipo de exame."
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def main():
    if not API_KEY:
        print("❌ ANTHROPIC_API_KEY não definida")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    client = anthropic.Anthropic(api_key=API_KEY)

    total = len(LAUDOS)
    print(f"Gerando {total} laudos completos em {OUTPUT_DIR}\n")

    for i, (tipo, variante, descricao) in enumerate(LAUDOS, 1):
        fname = f"{tipo}_{variante}.txt"
        fpath = OUTPUT_DIR / fname

        if fpath.exists():
            print(f"  [{i:3d}/{total}] SKIP (já existe) — {fname}")
            continue

        print(f"  [{i:3d}/{total}] Gerando — {fname}... ", end="", flush=True)
        try:
            laudo = gerar_laudo(client, tipo, variante, descricao)
            fpath.write_text(laudo, encoding="utf-8")
            print(f"✓ ({len(laudo.split())} palavras)")
        except Exception as e:
            print(f"❌ {e}")

        time.sleep(0.5)  # respeita rate limit

    print(f"\n✅ Concluído: {OUTPUT_DIR}")
    print("Próximo passo: python indexar_copiados.py  (adiciona 'sinteticos_completos' ao Qdrant)")


if __name__ == "__main__":
    main()
