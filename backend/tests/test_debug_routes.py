"""Cobertura do endpoint /debug/profile (admin only)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api.auth import UserContext
from backend.api.main import app, verify_token


def _client_as(role: str) -> TestClient:
    app.dependency_overrides[verify_token] = lambda: UserContext(
        id="u-1", email="x@y", display_name="t", role=role,
    )
    return TestClient(app)


def teardown_function(_):
    app.dependency_overrides.clear()


def test_profile_recusa_nao_admin():
    r = _client_as("medico").get("/debug/profile?duration=1")
    assert r.status_code == 403


def test_profile_admin_retorna_html():
    r = _client_as("admin").get("/debug/profile?duration=1")
    assert r.status_code == 200
    # pyinstrument output_html() inclui marcador identificável
    assert r.headers["content-type"].startswith("text/html")
    assert "<html" in r.text.lower() or "pyinstrument" in r.text.lower()


def test_profile_valida_duration_max():
    # duration > 30 → 422 (validação Query)
    r = _client_as("admin").get("/debug/profile?duration=999")
    assert r.status_code == 422
