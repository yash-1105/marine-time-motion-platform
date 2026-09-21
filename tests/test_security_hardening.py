import io
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

from apps.api.core.config import Settings
from apps.api.main import app
from apps.api.routers.ingestion import upload_file

PRINCIPAL = SimpleNamespace(data_scope=SimpleNamespace(tenant_id="tenant-security"))


def test_security_headers_present():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-correlation-id"]


def test_upload_rejects_unsupported_extension_before_processing():
    upload = UploadFile(filename="payload.exe", file=io.BytesIO(b"not a workbook"))
    with pytest.raises(HTTPException) as exc:
        upload_file(BackgroundTasks(), upload, None, PRINCIPAL)
    assert exc.value.status_code == 415


def test_upload_rejects_invalid_xlsx_container_before_processing():
    upload = UploadFile(filename="payload.xlsx", file=io.BytesIO(b"not-zip"))
    with pytest.raises(HTTPException) as exc:
        upload_file(BackgroundTasks(), upload, None, PRINCIPAL)
    assert exc.value.status_code == 415


def test_production_refuses_default_jwt_and_missing_cors():
    with pytest.raises(ValueError):
        Settings(_env_file=None, environment="production", jwt_secret_key="change-me", cors_origins="", cookie_secure=False)
