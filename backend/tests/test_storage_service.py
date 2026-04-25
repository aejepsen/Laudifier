"""Cobertura de StorageService — local + S3 + sanitization."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def storage_local(tmp_path, monkeypatch):
    """Recarrega o módulo apontando para tmp_path com USE_LOCAL=true."""
    monkeypatch.setenv("USE_LOCAL_STORAGE", "true")
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))
    import importlib

    from backend.services import storage_service
    importlib.reload(storage_service)
    return storage_service


# ── _sanitize_filename ───────────────────────────────────────────────────────

def test_sanitize_remove_path_traversal(storage_local):
    s = storage_local.StorageService._sanitize_filename
    assert s("../../etc/passwd") == "passwd"
    assert s("/abs/path/file.pdf") == "file.pdf"
    # Backslash não é separador no POSIX → vira underscore via regex
    assert "/" not in s("..\\..\\windows\\sys.dll")
    assert "\\" not in s("..\\..\\windows\\sys.dll")


def test_sanitize_substitui_caracteres_perigosos(storage_local):
    s = storage_local.StorageService._sanitize_filename
    # Espaço e ! viram _; \w em Py3 é Unicode (mantém acentos)
    out = s("laudo com espaços e ç!.pdf")
    assert " " not in out
    assert "!" not in out
    assert out.endswith(".pdf")


def test_sanitize_trunca_em_100_chars(storage_local):
    s = storage_local.StorageService._sanitize_filename
    longa = "a" * 200 + ".pdf"
    assert len(s(longa)) == 100


def test_sanitize_vazio_devolve_upload(storage_local):
    s = storage_local.StorageService._sanitize_filename
    # nome composto só de chars perigosos cai em fallback "upload"
    assert s("///") in {"upload", "_"}  # depende: "" → upload; "_" se algum char vira _


# ── upload_document local ────────────────────────────────────────────────────

def test_upload_local_grava_arquivo(storage_local, tmp_path):
    svc = storage_local.StorageService()
    path = svc.upload_document(b"binary content", "laudo.pdf", "user-001")
    assert os.path.exists(path)
    assert Path(path).read_bytes() == b"binary content"
    assert "user-001" in path
    assert path.endswith("laudo.pdf")


def test_upload_local_sanitiza_nome(storage_local):
    svc = storage_local.StorageService()
    path = svc.upload_document(b"x", "../evil.pdf", "u1")
    assert ".." not in Path(path).name
    assert Path(path).name == "evil.pdf"


def test_upload_local_isola_users(storage_local):
    svc = storage_local.StorageService()
    p1 = svc.upload_document(b"x", "a.pdf", "user-A")
    p2 = svc.upload_document(b"x", "a.pdf", "user-B")
    assert "user-A" in p1
    assert "user-B" in p2
    assert p1 != p2


# ── delete_document local ────────────────────────────────────────────────────

def test_delete_local_remove_arquivo(storage_local):
    svc = storage_local.StorageService()
    path = svc.upload_document(b"x", "tmp.pdf", "u1")
    assert os.path.exists(path)
    svc.delete_document(path)
    assert not os.path.exists(path)


def test_delete_local_arquivo_inexistente_nao_falha(storage_local):
    svc = storage_local.StorageService()
    svc.delete_document("/nonexistent/path/file.pdf")  # no-op


# ── modo S3 ──────────────────────────────────────────────────────────────────

def test_upload_s3(monkeypatch, tmp_path):
    """Branch S3: troca módulo para USE_LOCAL=false e mocka boto3."""
    monkeypatch.setenv("USE_LOCAL_STORAGE", "false")
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.test")
    monkeypatch.setenv("S3_BUCKET_LAUDOS", "test-bucket")
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))

    import importlib
    from backend.services import storage_service

    fake_client = MagicMock()
    monkeypatch.setattr(storage_service, "boto3", MagicMock(client=lambda *a, **kw: fake_client))
    importlib.reload(storage_service)
    # Após reload, refaz mock no novo módulo
    monkeypatch.setattr(storage_service, "boto3", MagicMock(client=lambda *a, **kw: fake_client))

    svc = storage_service.StorageService()
    url = svc.upload_document(b"data", "x.pdf", "u1")
    assert "https://s3.test/test-bucket/u1/" in url
    assert url.endswith("x.pdf")
    fake_client.put_object.assert_called_once()


def test_delete_s3_swallow_exception(monkeypatch, tmp_path):
    monkeypatch.setenv("USE_LOCAL_STORAGE", "false")
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://s3.test")
    monkeypatch.setenv("S3_BUCKET_LAUDOS", "test-bucket")
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))

    import importlib
    from backend.services import storage_service

    from botocore.exceptions import ClientError
    fake_client = MagicMock()
    fake_client.delete_object.side_effect = ClientError(
        {"Error": {"Code": "500", "Message": "boom"}}, "DeleteObject"
    )
    monkeypatch.setattr(storage_service, "boto3", MagicMock(client=lambda *a, **kw: fake_client))
    importlib.reload(storage_service)
    monkeypatch.setattr(storage_service, "boto3", MagicMock(client=lambda *a, **kw: fake_client))

    svc = storage_service.StorageService()
    # Não deve levantar
    svc.delete_document("https://s3.test/test-bucket/u1/abc/x.pdf")
    fake_client.delete_object.assert_called_once()


# ── teardown: restaura módulo no modo local ──────────────────────────────────

@pytest.fixture(autouse=True)
def _restore_storage_module(monkeypatch):
    yield
    monkeypatch.setenv("USE_LOCAL_STORAGE", "true")
    import importlib
    from backend.services import storage_service
    importlib.reload(storage_service)
