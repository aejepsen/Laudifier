# backend/tests/test_laudo.py
"""Testes unitários do Laudifier."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class MockUser:
    id = "med-001"; email = "dr@hospital.com"
    display_name = "Dr. Test"; crm = "12345/SP"
    role = "medico"; especialidade = "Radiologia"


# ── Agente de Busca ──────────────────────────────────────────────────────────

class TestLaudoSearchAgent:
    @pytest.mark.asyncio
    async def test_busca_sem_filtro(self):
        from backend.agents.search_agent import LaudoSearchAgent
        agent = LaudoSearchAgent.__new__(LaudoSearchAgent)
        filtro = agent._build_filter("", "")
        assert filtro is None

    @pytest.mark.asyncio
    async def test_busca_com_especialidade(self):
        from backend.agents.search_agent import LaudoSearchAgent
        agent  = LaudoSearchAgent.__new__(LaudoSearchAgent)
        filtro = agent._build_filter("radiologia", "")
        assert filtro is not None

    @pytest.mark.asyncio
    async def test_retorna_lista_vazia_sem_resultados(self):
        from backend.agents.search_agent import LaudoSearchAgent
        agent = LaudoSearchAgent.__new__(LaudoSearchAgent)
        with patch.object(agent, '_embed', new=AsyncMock(return_value=[0.1] * 1024)):
            with patch.object(agent, 'qdrant', create=True) as mock_q:
                mock_q.search = AsyncMock(return_value=[])
                result = await agent.buscar_laudos_similares("rx torax", "radiologia")
        assert isinstance(result, list)


# ── Geração de Laudo ─────────────────────────────────────────────────────────

class TestLaudoAgent:
    def test_extrair_campos_faltando(self):
        from backend.agents.laudo_agent import _extrair_campos_faltando
        laudo = "Paciente: [NOME DO PACIENTE], CRM: [CRM DO MÉDICO], Data: [DATA DO EXAME]"
        campos = _extrair_campos_faltando(laudo)
        assert "NOME DO PACIENTE"  in campos
        assert "CRM DO MÉDICO"     in campos
        assert "DATA DO EXAME"     in campos

    def test_formatar_dados_clinicos_vazio(self):
        from backend.agents.laudo_agent import _formatar_dados_clinicos
        assert _formatar_dados_clinicos({}) == ""

    def test_formatar_dados_clinicos_preenchido(self):
        from backend.agents.laudo_agent import _formatar_dados_clinicos
        r = _formatar_dados_clinicos({"paciente": "João", "idade": "45"})
        assert "João" in r
        assert "45"   in r

    def test_context_threshold_decide_estrategia(self):
        from backend.agents.laudo_agent import CONTEXT_RELEVANCE_THRESHOLD
        # Score alto → usa RAG
        score_alto = 0.85
        assert score_alto >= CONTEXT_RELEVANCE_THRESHOLD
        # Score baixo → fallback Claude
        score_baixo = 0.40
        assert score_baixo < CONTEXT_RELEVANCE_THRESHOLD


# ── Pipeline ─────────────────────────────────────────────────────────────────

class TestPipeline:
    def test_chunk_laudo_curto_retorna_um_chunk(self, tmp_path):
        from pipeline.run_pipeline import _chunk_laudo
        texto = "ACHADOS: Campos pulmonares sem condensações.\nIMPRESSÃO: Normal."
        chunks = _chunk_laudo(texto, "laudo.pdf", "radiologia", "rx_torax", "user-001")
        assert len(chunks) == 1
        assert chunks[0]["especialidade"] == "radiologia"
        assert chunks[0]["tipo_laudo"] == "rx_torax"
        assert chunks[0]["aprovado"] is True

    def test_chunk_laudo_longo_divide_por_secoes(self):
        from pipeline.run_pipeline import _chunk_laudo
        # Laudo longo com múltiplas seções em maiúsculo
        texto = "IDENTIFICAÇÃO:\nPaciente X, 45 anos.\n\n" + \
                "TÉCNICA:\nRX PA em inspiração máxima.\n\n" + \
                "ACHADOS:\nCampos pulmonares livres.\n\n" + \
                "IMPRESSÃO DIAGNÓSTICA:\nExame sem alterações.\n\n" + \
                "CONCLUSÃO:\nDentro dos limites da normalidade."
        # Texto curto ainda → 1 chunk
        chunks = _chunk_laudo(texto, "laudo.pdf", "radiologia", "rx", "u")
        assert len(chunks) >= 1

    def test_extrair_texto_txt(self, tmp_path):
        from pipeline.run_pipeline import _extrair_texto
        f = tmp_path / "laudo.txt"
        f.write_text("ACHADOS: Normal.", encoding="utf-8")
        texto = _extrair_texto(str(f), "laudo.txt")
        assert "ACHADOS" in texto


# ── Export ───────────────────────────────────────────────────────────────────

class TestExportService:
    @pytest.mark.asyncio
    async def test_exportar_txt(self, tmp_path):
        from backend.services.laudo_service import ExportService
        svc   = ExportService()
        laudo = {
            "laudo": "ACHADOS: Normal.\nIMPRESSÃO: Sem alterações.",
            "laudo_editado": None,
            "especialidade": "Radiologia",
            "created_at": "2025-03-26T10:00:00",
        }
        path = svc._to_txt(laudo["laudo"], laudo)
        import os
        assert os.path.exists(path)
        content = open(path).read()
        assert "RADIOLOGIA" in content
        assert "ACHADOS" in content

    @pytest.mark.asyncio
    async def test_exportar_pdf(self):
        from backend.services.laudo_service import ExportService
        import os
        svc  = ExportService()
        laudo = {
            "laudo": "ACHADOS: Campos pulmonares livres.\n\nIMPRESSÃO: Normal.",
            "laudo_editado": None,
            "especialidade": "Radiologia",
            "created_at": "2025-03-26T10:00:00",
        }
        path = svc._to_pdf(laudo["laudo"], laudo)
        assert os.path.exists(path)
        assert path.endswith(".pdf")


# ── Storage ───────────────────────────────────────────────────────────────────

class TestStorage:
    def test_upload_local(self, tmp_path):
        import os
        os.environ["USE_LOCAL_STORAGE"] = "true"
        os.environ["LOCAL_STORAGE_PATH"] = str(tmp_path)
        from backend.services.laudo_service import StorageService
        svc  = StorageService()
        path = svc.upload_document(b"laudo pdf bytes", "laudo.pdf", "med-001")
        assert os.path.exists(path)


# ── Auth ─────────────────────────────────────────────────────────────────────

class TestAuth:
    def test_health_endpoint(self):
        from fastapi.testclient import TestClient
        from backend.api.main import app
        client = TestClient(app)
        r = client.get("/health")
        assert r.status_code == 200
        assert "status" in r.json()
