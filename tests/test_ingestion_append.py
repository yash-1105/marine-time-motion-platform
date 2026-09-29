"""Focused coverage for atomic active-dataset workbook append semantics."""

import shutil
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import func, select

from apps.api.core.config import settings
from apps.api.core.database import SessionLocal
from apps.api.main import app
from apps.api.models.canonical import VesselCall
from apps.api.services.auth_service import create_user_session
from apps.api.services.ingestion.synthetic import reset_tenant_dataset
from apps.worker.main import process_ingestion_analytics_task


def _workbook_bytes(vcn: str, *, valid: bool = True) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "VesselCalls"
    sheet.append(["VCN", "Vessel_Name"] if valid else ["VCN"])
    sheet.append([vcn, f"Vessel {vcn}"] if valid else [vcn])
    output = BytesIO()
    book.save(output)
    return output.getvalue()


def _files(items: list[tuple[str, bytes]]):
    return [
        (
            "files",
            (name, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        )
        for name, content in items
    ]


@pytest.fixture
def append_environment(monkeypatch):
    db = SessionLocal()
    client = TestClient(app)
    tenant_id = f"append-{uuid4().hex[:10]}"
    session = create_user_session(
        db=db,
        user_id=f"user-{tenant_id}",
        email=f"{tenant_id}@example.test",
        roles=[],
        permissions=["view", "create"],
        data_scope={"tenant_id": tenant_id, "port_id": "*", "terminal_id": "*"},
    )
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    monkeypatch.setattr(
        "apps.api.routers.ingestion.process_ingestion_analytics_task.send",
        lambda batch_id, tenant, checksum: process_ingestion_analytics_task.fn(batch_id, tenant, checksum),
    )
    yield db, client, tenant_id, headers
    db.rollback()
    reset_tenant_dataset(db, tenant_id)
    db.commit()
    db.close()
    shutil.rmtree(Path(settings.ingestion_storage_path) / tenant_id, ignore_errors=True)


def _active(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.get("/api/v1/ingestion/active", headers=headers)
    assert response.status_code == 200
    assert response.json()["has_active_dataset"] is True
    return response.json()["batch"]


def _active_call_count(db, tenant_id: str) -> int:
    db.expire_all()
    return db.scalar(
        select(func.count()).select_from(VesselCall).where(
            VesselCall.tenant_id == tenant_id,
            VesselCall.is_merged.is_(False),
        )
    )


def test_append_preserves_manifest_refresh_analytics_deduplication_and_failure_rollback(append_environment):
    db, client, tenant_id, headers = append_environment
    a = _workbook_bytes("APPEND-A")
    b = _workbook_bytes("APPEND-B")
    c = _workbook_bytes("APPEND-C")
    d = _workbook_bytes("APPEND-D")
    e = _workbook_bytes("APPEND-E")

    initial = client.post("/api/v1/ingestion/upload", headers=headers, files=_files([("a.xlsx", a), ("b.xlsx", b)]))
    assert initial.status_code == 202
    first_batch = _active(client, headers)
    assert first_batch["file_count"] == 2
    assert _active_call_count(db, tenant_id) == 2

    append_one = client.post("/api/v1/ingestion/append", headers=headers, files=_files([("c.xlsx", c)]))
    assert append_one.status_code == 202
    assert append_one.json()["file_count"] == 3
    assert append_one.json()["added_file_count"] == 1
    second_batch = _active(client, headers)
    assert second_batch["batch_id"] != first_batch["batch_id"]
    assert {item["filename"] for item in second_batch["files"]} == {"a.xlsx", "b.xlsx", "c.xlsx"}
    assert _active_call_count(db, tenant_id) == 3

    append_two = client.post(
        "/api/v1/ingestion/append",
        headers=headers,
        files=_files([("d.xlsx", d), ("e.xlsx", e)]),
    )
    assert append_two.status_code == 202
    refreshed = _active(client, headers)
    assert refreshed["file_count"] == 5
    assert {item["filename"] for item in refreshed["files"]} == {
        "a.xlsx", "b.xlsx", "c.xlsx", "d.xlsx", "e.xlsx"
    }
    assert _active_call_count(db, tenant_id) == 5

    duplicate = client.post(
        "/api/v1/ingestion/append",
        headers=headers,
        files=_files([("same-content-different-name.xlsx", a)]),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "DUPLICATE_WORKBOOK"
    assert _active(client, headers)["batch_id"] == refreshed["batch_id"]
    assert _active(client, headers)["file_count"] == 5
    assert _active_call_count(db, tenant_id) == 5

    failed = client.post(
        "/api/v1/ingestion/append",
        headers=headers,
        files=_files([("malformed.xlsx", _workbook_bytes("BROKEN", valid=False))]),
    )
    assert failed.status_code == 422
    after_failure = _active(client, headers)
    assert after_failure["batch_id"] == refreshed["batch_id"]
    assert after_failure["file_count"] == 5
    assert _active_call_count(db, tenant_id) == 5


def test_append_enforces_fifteen_file_limit_across_active_group(append_environment):
    _db, client, _tenant_id, headers = append_environment
    initial_items = [(f"source-{index}.xlsx", _workbook_bytes(f"LIMIT-{index}")) for index in range(1, 14)]
    initial = client.post("/api/v1/ingestion/upload", headers=headers, files=_files(initial_items))
    assert initial.status_code == 202
    assert _active(client, headers)["file_count"] == 13

    rejected = client.post(
        "/api/v1/ingestion/append",
        headers=headers,
        files=_files(
            [
                ("source-14.xlsx", _workbook_bytes("LIMIT-14")),
                ("source-15.xlsx", _workbook_bytes("LIMIT-15")),
                ("source-16.xlsx", _workbook_bytes("LIMIT-16")),
            ]
        ),
    )
    assert rejected.status_code == 400
    assert _active(client, headers)["file_count"] == 13

    accepted = client.post(
        "/api/v1/ingestion/append",
        headers=headers,
        files=_files(
            [
                ("source-14.xlsx", _workbook_bytes("LIMIT-14")),
                ("source-15.xlsx", _workbook_bytes("LIMIT-15")),
            ]
        ),
    )
    assert accepted.status_code == 202
    active = _active(client, headers)
    assert active["file_count"] == 15
    assert _active(client, headers)["batch_id"] == active["batch_id"]
    assert _active(client, headers)["file_count"] == 15
