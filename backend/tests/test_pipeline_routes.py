"""Cobertura de api/pipeline_routes — admin endpoints + chunking."""
from __future__ import annotations

import io
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.api import pipeline_routes as pr


# ── _chunk ───────────────────────────────────────────────────────────────────

def test_chunk_vazio_retorna_lista_vazia():
    assert pr._chunk("") == []
    assert pr._chunk("   ") == []


def test_chunk_secoes_uppercase():
    texto = (
        "ACHADOS:\n" + "x " * 40 + "\n"
        "IMPRESSÃO:\n" + "y " * 40 + "\n"
    )
    chunks = pr._chunk(texto)
    assert len(chunks) >= 1
    assert any("ACHADOS" in c for c in chunks)


def test_chunk_sem_secoes_quebra_por_tamanho():
    texto = "palavra " * 500  # ~4000 chars > CHUNK_SIZE=1500
    chunks = pr._chunk(texto)
    assert len(chunks) > 1
    # Overlap não deve duplicar tudo
    assert all(len(c.strip()) > 50 for c in chunks)


def test_chunk_descarta_blocos_curtos():
    chunks = pr._chunk("curto")  # < 50 chars
    assert chunks == []


# ── _limpar ──────────────────────────────────────────────────────────────────

def test_limpar_remove_header_ate_separator():
    raw = "Header line\n=== separator ===\nConteúdo real"
    assert pr._limpar(raw) == "Conteúdo real"


def test_limpar_sem_separator_devolve_original():
    raw = "sem separador"
    assert pr._limpar(raw) == "sem separador"


# ── _check_admin ─────────────────────────────────────────────────────────────

def test_check_admin_sem_chave_no_env_recusa(monkeypatch):
    monkeypatch.setattr(pr, "ADMIN_KEY", "")
    with pytest.raises(HTTPException) as exc:
        pr._check_admin("any")
    assert exc.value.status_code == 403


def test_check_admin_chave_errada_recusa(monkeypatch):
    monkeypatch.setattr(pr, "ADMIN_KEY", "secret")
    with pytest.raises(HTTPException) as exc:
        pr._check_admin("wrong")
    assert exc.value.status_code == 403


def test_check_admin_chave_correta_passa(monkeypatch):
    monkeypatch.setattr(pr, "ADMIN_KEY", "secret")
    pr._check_admin("secret")  # não levanta


# ── /status ──────────────────────────────────────────────────────────────────

@pytest.fixture
def admin_client(monkeypatch):
    monkeypatch.setattr(pr, "ADMIN_KEY", "test-admin-key")
    fake = MagicMock()
    fake.get_collection.return_value = MagicMock(points_count=42)
    monkeypatch.setattr(pr, "_get_client", lambda: fake)

    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(pr.router)
    return TestClient(app), fake


def test_status_sem_header_403(admin_client):
    client, _ = admin_client
    r = client.get("/admin/pipeline/status")
    assert r.status_code == 422  # FastAPI: header obrigatório ausente


def test_status_chave_errada_403(admin_client):
    client, _ = admin_client
    r = client.get("/admin/pipeline/status", headers={"X-Admin-Key": "wrong"})
    assert r.status_code == 403


def test_status_ok(admin_client):
    client, fake = admin_client
    r = client.get("/admin/pipeline/status", headers={"X-Admin-Key": "test-admin-key"})
    assert r.status_code == 200
    data = r.json()
    assert data["points"] == 42
    assert data["collection"] == pr.COLLECTION


# ── /indexar ─────────────────────────────────────────────────────────────────

def test_indexar_processa_e_chama_upsert(admin_client, monkeypatch):
    client, fake = admin_client
    fake_model = MagicMock()
    # Retorna 2 vetores compatíveis com 2 chunks
    fake_model.encode.return_value = np.array([[0.1] * 1024, [0.2] * 1024])
    monkeypatch.setattr(pr, "_get_model", lambda: fake_model)

    texto = (
        "ACHADOS:\n" + "x " * 40 + "\n"
        "IMPRESSÃO:\n" + "y " * 40 + "\n"
    )
    files = {"files": ("laudo.txt", io.BytesIO(texto.encode("utf-8")), "text/plain")}
    r = client.post(
        "/admin/pipeline/indexar",
        files=files,
        data={"especialidade": "radiologia", "source": "upload"},
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["files_indexed"] == 1
    assert body["chunks_indexed"] >= 1
    fake.upsert.assert_called()


def test_indexar_arquivo_vazio_pula(admin_client, monkeypatch):
    client, fake = admin_client
    fake_model = MagicMock()
    fake_model.encode.return_value = np.array([])
    monkeypatch.setattr(pr, "_get_model", lambda: fake_model)

    files = {"files": ("vazio.txt", io.BytesIO(b""), "text/plain")}
    r = client.post(
        "/admin/pipeline/indexar",
        files=files,
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    assert r.json()["files_indexed"] == 0


def test_indexar_captura_erro_por_arquivo(admin_client, monkeypatch):
    client, fake = admin_client
    fake_model = MagicMock()
    fake_model.encode.side_effect = RuntimeError("modelo morreu")
    monkeypatch.setattr(pr, "_get_model", lambda: fake_model)

    texto = "ACHADOS:\n" + "x " * 40
    files = {"files": ("erro.txt", io.BytesIO(texto.encode()), "text/plain")}
    r = client.post(
        "/admin/pipeline/indexar",
        files=files,
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["errors"]) == 1
    assert body["errors"][0]["file"] == "erro.txt"


# ── /limpar ──────────────────────────────────────────────────────────────────

def test_limpar_colecao(admin_client):
    client, fake = admin_client
    r = client.delete("/admin/pipeline/limpar", headers={"X-Admin-Key": "test-admin-key"})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    fake.delete.assert_called_once()
