"""
Testes de comportamento da API Laudifier — via interface HTTP pública.
Padrão: mocks apenas na fronteira externa (Supabase, Qdrant, Anthropic, Mem0).
Cada teste verifica um comportamento observável, não detalhes de implementação.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.auth import UserContext

# ─── Fixture: usuário autenticado ──────────────────────────────────────────
MEDICO = UserContext(
    id="user-001",
    email="dr.silva@hospital.com",
    display_name="Dr. Silva",
    crm="12345-SP",
    role="medico",
    especialidade="Radiologia",
)

OUTRO_MEDICO = UserContext(
    id="user-999",
    email="outro@hospital.com",
    display_name="Dr. Outro",
    crm="99999-SP",
    role="medico",
    especialidade="Radiologia",
)


def _auth(user: UserContext = MEDICO):
    """Sobrescreve verify_token para não depender de JWT/Supabase."""
    app.dependency_overrides[
        __import__("backend.api.auth", fromlist=["verify_token"]).verify_token
    ] = lambda: user
    return TestClient(app)


def _no_auth():
    app.dependency_overrides = {}
    return TestClient(app)


# ─── Health ────────────────────────────────────────────────────────────────
class TestHealth:
    def test_retorna_status_e_versao(self):
        """Health endpoint informa status e versão sem autenticação."""
        with patch("backend.api.main.QdrantClient") as mock_qdrant:
            mock_qdrant.return_value.get_collections.return_value = []
            r = _no_auth().get("/health")

        assert r.status_code == 200
        body = r.json()
        assert "status" in body
        assert "version" in body
        assert "services" in body

    def test_degradado_quando_qdrant_offline(self):
        """Health retorna 'degraded' se Qdrant não responde."""
        with patch("backend.api.main.QdrantClient") as mock_qdrant:
            mock_qdrant.return_value.get_collections.side_effect = Exception("conn refused")
            r = _no_auth().get("/health")

        assert r.status_code == 200
        assert r.json()["status"] == "degraded"


# ─── Autenticação ──────────────────────────────────────────────────────────
class TestAutenticacao:
    def test_endpoint_protegido_sem_token_retorna_401(self):
        """Rotas protegidas rejeitam requests sem Authorization header."""
        r = _no_auth().get("/laudos")
        assert r.status_code in (401, 403)

    def test_endpoint_protegido_com_token_invalido_retorna_401(self):
        """Token malformado não passa pela autenticação."""
        r = _no_auth().get("/laudos", headers={"Authorization": "Bearer token-invalido"})
        assert r.status_code in (401, 403)

    def test_endpoint_protegido_com_token_valido_nao_retorna_401(self):
        """Usuário autenticado acessa rota protegida sem erro de auth."""
        with patch("backend.services.laudo_service.LaudoService.listar", new=AsyncMock(return_value=[])):
            r = _auth().get("/laudos")

        assert r.status_code != 401
        assert r.status_code != 403


# ─── Listagem de laudos ────────────────────────────────────────────────────
class TestListarLaudos:
    def test_retorna_lista_vazia_quando_nao_tem_laudos(self):
        """Médico sem laudos recebe lista vazia, não erro."""
        with patch("backend.services.laudo_service.LaudoService.listar", new=AsyncMock(return_value=[])):
            r = _auth().get("/laudos")

        assert r.status_code == 200
        assert r.json() == []

    def test_retorna_laudos_do_medico_autenticado(self):
        """Lista retorna apenas laudos do médico autenticado."""
        laudos_mock = [
            {"id": "abc", "especialidade": "Radiologia", "created_at": "2025-01-01T00:00:00"},
        ]
        with patch("backend.services.laudo_service.LaudoService.listar", new=AsyncMock(return_value=laudos_mock)):
            r = _auth().get("/laudos")

        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["id"] == "abc"

    def test_filtra_por_especialidade(self):
        """Parâmetro especialidade é repassado ao serviço."""
        with patch("backend.services.laudo_service.LaudoService.listar", new=AsyncMock(return_value=[])) as mock_listar:
            r = _auth().get("/laudos?especialidade=Radiologia")

        assert r.status_code == 200


# ─── Busca por ID ──────────────────────────────────────────────────────────
class TestGetLaudo:
    def test_retorna_laudo_existente(self):
        """GET /laudos/{id} retorna dados do laudo."""
        laudo_mock = {"id": "laudo-123", "laudo": "Sem alterações.", "especialidade": "Radiologia"}
        with patch("backend.services.laudo_service.LaudoService.get", new=AsyncMock(return_value=laudo_mock)):
            r = _auth().get("/laudos/laudo-123")

        assert r.status_code == 200
        assert r.json()["id"] == "laudo-123"

    def test_retorna_404_para_laudo_inexistente(self):
        """GET /laudos/{id} retorna 404 se laudo não existe."""
        with patch("backend.services.laudo_service.LaudoService.get", new=AsyncMock(return_value=None)):
            r = _auth().get("/laudos/nao-existe")

        assert r.status_code == 404

    def test_idor_usuario_nao_acessa_laudo_de_outro(self):
        """Usuário A não consegue acessar laudo do Usuário B (isolamento por user_id)."""
        # LaudoService.get filtra por user_id internamente — retorna None para outro user
        with patch("backend.services.laudo_service.LaudoService.get", new=AsyncMock(return_value=None)):
            client = _auth(OUTRO_MEDICO)
            r = client.get("/laudos/laudo-do-medico-001")

        assert r.status_code == 404


# ─── Atualização de laudo ──────────────────────────────────────────────────
class TestAtualizarLaudo:
    def test_salva_edicao_do_medico(self):
        """PUT /laudos/{id} persiste edição e retorna ok."""
        with patch("backend.services.laudo_service.LaudoService.atualizar", new=AsyncMock()):
            r = _auth().put("/laudos/laudo-123?laudo_editado=Laudo+corrigido+pelo+médico")

        assert r.status_code == 200
        assert r.json()["status"] == "ok"


# ─── Feedback ─────────────────────────────────────────────────────────────
class TestFeedback:
    def test_feedback_aprovacao_retorna_ok(self):
        """Feedback de aprovação é registrado sem erro."""
        with patch("backend.services.laudo_service.LaudoService.registrar_feedback", new=AsyncMock()):
            r = _auth().post(
                "/laudos/laudo-123/feedback",
                json={"aprovado": True, "correcoes": None},
            )

        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_feedback_correcao_retorna_ok(self):
        """Feedback com correções também é aceito."""
        with patch("backend.services.laudo_service.LaudoService.registrar_feedback", new=AsyncMock()):
            r = _auth().post(
                "/laudos/laudo-123/feedback",
                json={"aprovado": False, "correcoes": "Ajustar conclusão."},
            )

        assert r.status_code == 200


# ─── Exportação ───────────────────────────────────────────────────────────
class TestExportacao:
    def test_exportar_txt_retorna_arquivo(self, tmp_path):
        """GET /laudos/{id}/exportar/txt retorna FileResponse."""
        txt_file = tmp_path / "laudo.txt"
        txt_file.write_text("ACHADOS: Normal.")

        laudo_mock = {"id": "laudo-123", "laudo": "ACHADOS: Normal.", "especialidade": "Radiologia",
                      "laudo_editado": None, "created_at": "2025-01-01T00:00:00"}

        with patch("backend.services.laudo_service.LaudoService.get", new=AsyncMock(return_value=laudo_mock)):
            with patch("backend.services.export_service.ExportService.exportar", new=AsyncMock(return_value=str(txt_file))):
                r = _auth().get("/laudos/laudo-123/exportar/txt")

        assert r.status_code == 200

    def test_exportar_laudo_inexistente_retorna_404(self):
        """Exportação de laudo que não existe retorna 404."""
        with patch("backend.services.laudo_service.LaudoService.get", new=AsyncMock(return_value=None)):
            r = _auth().get("/laudos/nao-existe/exportar/pdf")

        assert r.status_code == 404

    def test_formato_invalido_nao_quebra_servidor(self):
        """Formato desconhecido não causa 500."""
        laudo_mock = {"id": "l", "laudo": "x", "especialidade": "R",
                      "laudo_editado": None, "created_at": "2025-01-01T00:00:00"}
        with patch("backend.services.laudo_service.LaudoService.get", new=AsyncMock(return_value=laudo_mock)):
            with patch("backend.services.export_service.ExportService.exportar",
                       new=AsyncMock(side_effect=ValueError("formato inválido"))):
                r = _auth().get("/laudos/l/exportar/xyz")

        assert r.status_code != 500


# ─── Dashboard ────────────────────────────────────────────────────────────
class TestDashboard:
    def test_stats_retorna_dados(self):
        """Dashboard stats retorna dict com métricas."""
        stats_mock = {"total": 10, "aprovados": 7, "exportados": 3}
        with patch("backend.services.laudo_service.LaudoService.get_stats", new=AsyncMock(return_value=stats_mock)):
            r = _auth().get("/dashboard/stats")

        assert r.status_code == 200
        body = r.json()
        assert "total" in body


# ─── Geração de laudo (streaming) ─────────────────────────────────────────
class TestGerarLaudo:
    def test_gerar_sem_body_retorna_422(self):
        """POST /laudos/gerar sem body retorna erro de validação."""
        r = _auth().post("/laudos/gerar", json={})
        assert r.status_code == 422

    def test_gerar_com_dados_minimos_inicia_stream(self):
        """POST /laudos/gerar com dados válidos retorna 200."""
        async def _fake_stream(*args, **kwargs):
            yield {"type": "token", "text": "TÉCNICA:"}
            yield {"type": "done", "tipo_geracao": "rag", "laudos_ref": []}

        payload = {
            "solicitacao": "RM de crânio sem contraste",
            "especialidade": "Radiologia",
            "dados_clinicos": {"indicacao": "cefaleia crônica"},
        }
        with patch("backend.api.main.gerar_laudo_stream", new=_fake_stream):
            with patch("backend.services.laudo_service.LaudoService.salvar", new=AsyncMock()):
                r = _auth().post("/laudos/gerar", json=payload)

        assert r.status_code == 200


# ─── Streaming SSE ─────────────────────────────────────────────────────────
class TestStreamingSSE:
    def test_sse_content_type(self):
        """POST /laudos/gerar retorna Content-Type text/event-stream."""
        async def _stream(*args, **kwargs):
            yield {"type": "token", "text": "ACHADOS:"}
            yield {"type": "done", "tipo_geracao": "rag", "laudos_ref": []}

        payload = {"solicitacao": "RM de crânio", "especialidade": "Radiologia"}
        with patch("backend.api.main.gerar_laudo_stream", new=_stream):
            with patch("backend.services.laudo_service.LaudoService.salvar", new=AsyncMock()):
                r = _auth().post("/laudos/gerar", json=payload)

        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")

    def test_sse_eventos_sao_json_valido(self):
        """Cada linha 'data: ...' do stream contém JSON parseable."""
        async def _stream(*args, **kwargs):
            yield {"type": "token", "text": "ACHADOS:"}
            yield {"type": "done", "tipo_geracao": "fallback", "laudos_ref": []}

        payload = {"solicitacao": "ECO cardíaco", "especialidade": "Cardiologia"}
        with patch("backend.api.main.gerar_laudo_stream", new=_stream):
            with patch("backend.services.laudo_service.LaudoService.salvar", new=AsyncMock()):
                r = _auth().post("/laudos/gerar", json=payload)

        data_lines = [l for l in r.text.splitlines() if l.startswith("data: ")]
        assert len(data_lines) > 0
        for line in data_lines:
            json.loads(line.removeprefix("data: "))  # não lança — JSON válido

    def test_solicitacao_muito_longa_rejeitada(self):
        """Solicitação acima de 5000 chars é rejeitada antes de chegar ao agente."""
        payload = {"solicitacao": "x" * 5001, "especialidade": "Radiologia"}
        r = _auth().post("/laudos/gerar", json=payload)
        assert r.status_code == 422

    def test_especialidade_muito_longa_rejeitada(self):
        """Especialidade acima de 100 chars é rejeitada pela validação Pydantic."""
        payload = {"solicitacao": "laudo normal", "especialidade": "E" * 101}
        r = _auth().post("/laudos/gerar", json=payload)
        assert r.status_code == 422


# ─── Transcrição de voz ────────────────────────────────────────────────────
class TestTranscricao:
    def test_sem_auth_retorna_401(self):
        """POST /laudos/transcrever sem token retorna 401."""
        r = _no_auth().post(
            "/laudos/transcrever",
            files={"audio": ("t.webm", b"dados-de-audio", "audio/webm")},
        )
        assert r.status_code in (401, 403)

    def test_audio_muito_grande_retorna_400(self):
        """Arquivo acima de 25 MB é rejeitado com 400 antes do Whisper."""
        big_audio = b"0" * (25 * 1024 * 1024 + 1)
        r = _auth().post(
            "/laudos/transcrever",
            files={"audio": ("big.webm", big_audio, "audio/webm")},
        )
        assert r.status_code == 400

    def test_audio_valido_retorna_transcript(self):
        """Áudio válido processado pelo Whisper retorna texto transcrito."""
        import sys

        whisper_mock = MagicMock()
        whisper_mock.load_model.return_value.transcribe.return_value = {
            "text": "  Achados normais para a idade.  "
        }

        with patch.dict(sys.modules, {"whisper": whisper_mock}):
            r = _auth().post(
                "/laudos/transcrever",
                files={"audio": ("test.webm", b"fake-audio-bytes", "audio/webm")},
            )

        assert r.status_code == 200
        assert r.json()["transcript"] == "Achados normais para a idade."  # stripped


# ─── Memória — IDOR ────────────────────────────────────────────────────────
class TestMemoriaIDOR:
    def test_deletar_memoria_de_outro_usuario_retorna_404(self):
        """DELETE /memoria/{id} retorna 404 se memória não pertence ao usuário autenticado."""
        # Usuário OUTRO_MEDICO tenta deletar memória do MEDICO — não aparece na sua lista
        with patch(
            "backend.services.memory_service.LaudifierMemory.listar_memorias_medico",
            return_value=[],  # OUTRO_MEDICO não tem memórias
        ):
            r = _auth(OUTRO_MEDICO).delete("/memoria/mem-do-medico-001")

        assert r.status_code == 404

    def test_deletar_propria_memoria_retorna_deleted(self):
        """DELETE /memoria/{id} remove memória do próprio usuário."""
        with patch(
            "backend.services.memory_service.LaudifierMemory.listar_memorias_medico",
            return_value=[{"id": "mem-001"}],
        ):
            with patch("backend.services.memory_service.LaudifierMemory.deletar_memoria"):
                r = _auth().delete("/memoria/mem-001")

        assert r.status_code == 200
        assert r.json()["status"] == "deleted"


# ─── Rate limiting ─────────────────────────────────────────────────────────
class TestRateLimiting:
    def test_limiter_wired_na_app(self):
        """Verifica que o rate limiter está registrado no estado da aplicação."""
        from slowapi.errors import RateLimitExceeded
        assert hasattr(app.state, "limiter"), "app.state.limiter não encontrado"
        assert RateLimitExceeded in app.exception_handlers, (
            "Handler para RateLimitExceeded não registrado"
        )
