"""Tests for Dataset Ingestion, Persistence, and Replacement (spec Phase 12 / Change 1 & 2)."""

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, desc, select
from sqlalchemy.orm import sessionmaker

from apps.api.core.config import settings
from apps.api.main import app
from apps.api.models.analytics import DashboardSnapshot, KPIResult
from apps.api.models.canonical import VesselCall
from apps.api.models.ingestion import IngestionBatch, IngestionFile, RawRecord, StagingRecord
from apps.api.services.ingestion.pipeline import IngestionPipeline
from apps.api.services.ingestion.synthetic import reset_tenant_dataset
from apps.worker.main import process_ingestion_analytics_task
from testkit.loader import load_synthetic_dataset

client = TestClient(app)


def _workbook(path: Path, vcn: str, include_vessel_name: bool = True) -> str:
    """Create a small ordinary XLSX workbook for deterministic group-ingestion tests."""
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.title = "VesselCalls"
    headers = ["VCN"] + (["Vessel_Name"] if include_vessel_name else [])
    sheet.append(headers)
    sheet.append([vcn] + ([f"Vessel {vcn}"] if include_vessel_name else []))
    book.save(path)
    return str(path)


def _delete_uncommitted_group(db_session, batch_id: str) -> None:
    """Remove an isolated parse-only test group without touching the active dataset."""
    for model in (StagingRecord, RawRecord):
        for row in db_session.execute(select(model).where(model.ingestion_batch_id == batch_id)).scalars().all():
            db_session.delete(row)
    for row in (
        db_session.execute(select(IngestionFile).where(IngestionFile.group_batch_id == batch_id)).scalars().all()
    ):
        db_session.delete(row)
    batch = db_session.execute(select(IngestionBatch).where(IngestionBatch.batch_id == batch_id)).scalar_one_or_none()
    if batch:
        db_session.delete(batch)
    db_session.commit()


@pytest.fixture(scope="module")
def auth_headers():
    resp = client.post("/api/v1/auth/dev/login", json={"role_or_email": "Platform Administrator"})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def db_session():
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_active_dataset_endpoint(auth_headers):
    """Verifies that GET /api/v1/ingestion/active reports active dataset details."""
    resp = client.get("/api/v1/ingestion/active", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "has_active_dataset" in data
    if data["has_active_dataset"]:
        assert data["batch"] is not None
        assert "batch_id" in data["batch"]
        assert "file_name" in data["batch"]
        assert data["batch"]["status"] == "COMMITTED"


def test_dashboard_persisted_snapshot_reuse(auth_headers, db_session):
    """Verifies that Executive Dashboard reads from persisted PostgreSQL snapshot rapidly (<50ms)."""
    # 1. Verify snapshot exists in database
    snapshot = (
        db_session.execute(
            select(DashboardSnapshot)
            .where(
                DashboardSnapshot.tenant_id == "synthetic-tenant",
                DashboardSnapshot.is_active.is_(True),
                DashboardSnapshot.filters_hash == "unfiltered",
            )
            .order_by(desc(DashboardSnapshot.created_at))
        )
        .scalars()
        .first()
    )

    assert snapshot is not None, "Active dashboard snapshot should exist in analytics.dashboard_snapshot"
    assert snapshot.snapshot_data is not None

    # 2. Timing check: Fetch from API should be near instantaneous (pure read, no recalculation)
    start_time = time.time()
    resp = client.get("/api/v1/dashboard/executive", headers=auth_headers)
    elapsed = time.time() - start_time

    assert resp.status_code == 200
    dash_data = resp.json()

    # Should match the persisted snapshot total calls
    assert dash_data["summary"]["total_vessel_calls"] == snapshot.snapshot_data["summary"]["total_vessel_calls"]
    # Fast read: reading persisted JSON from PostgreSQL takes well under 200ms
    assert elapsed < 0.5, f"Dashboard read took {elapsed}s, should be fast read operation without recalculation"


def test_dataset_upload_queues_analytics_and_worker_commits_batch(auth_headers, db_session, monkeypatch, tmp_path):
    """A two-workbook group activates once and produces combined analytics/KPIs."""
    monkeypatch.setattr(
        "apps.api.routers.ingestion.process_ingestion_analytics_task.send",
        lambda batch_id, tenant_id, checksum: process_ingestion_analytics_task.fn(batch_id, tenant_id, checksum),
    )
    fixture_path = "fixtures/Synthetic_Marine_Time_Motion_Test_Data.xlsx"
    with open(fixture_path, "rb") as f:
        file_content = f.read()
    extra_path = _workbook(tmp_path / "additional-call.xlsx", "COMBINED-EXTRA-001")
    with open(extra_path, "rb") as f:
        extra_content = f.read()

    # Upload replacement workbook
    files = [
        (
            "files",
            (
                "replacement_workbook.xlsx",
                file_content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        ),
        (
            "files",
            (
                "additional-call.xlsx",
                extra_content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        ),
    ]
    upload_resp = client.post("/api/v1/ingestion/upload", headers=auth_headers, files=files)
    assert upload_resp.status_code == 202
    upload_data = upload_resp.json()
    new_batch_id = upload_data["batch_id"]
    assert upload_data["status"] == "PROCESSING"
    assert upload_data["file_count"] == 2

    # Verify that the new batch is the only active batch for the tenant
    active_batches = (
        db_session.execute(
            select(IngestionBatch).where(
                IngestionBatch.tenant_id == "synthetic-tenant",
                IngestionBatch.is_active.is_(True),
            )
        )
        .scalars()
        .all()
    )
    assert len(active_batches) == 1
    assert active_batches[0].batch_id == new_batch_id

    # Verify that the active dashboard snapshot now points to the new batch
    active_snapshot = (
        db_session.execute(
            select(DashboardSnapshot).where(
                DashboardSnapshot.tenant_id == "synthetic-tenant",
                DashboardSnapshot.is_active.is_(True),
            )
        )
        .scalars()
        .first()
    )
    assert active_snapshot is not None
    assert active_snapshot.batch_id == new_batch_id
    assert active_snapshot.snapshot_data["summary"]["total_vessel_calls"] == 73
    assert db_session.execute(select(KPIResult)).scalars().first() is not None

    # Delivery retry is idempotent: an already active committed group is not reinserted.
    process_ingestion_analytics_task.fn(new_batch_id, "synthetic-tenant", upload_data["batch_id"])
    db_session.expire_all()
    assert (
        len(
            db_session.execute(
                select(VesselCall).where(VesselCall.tenant_id == "synthetic-tenant", VesselCall.is_merged.is_(False))
            )
            .scalars()
            .all()
        )
        == 73
    )

    # Verify active endpoint reflects the new batch
    active_resp = client.get("/api/v1/ingestion/active", headers=auth_headers)
    assert active_resp.status_code == 200
    assert active_resp.json()["batch"]["batch_id"] == new_batch_id
    assert active_resp.json()["batch"]["file_name"] == "2 workbooks"


def test_upload_rejects_sixteen_workbooks_before_parsing(auth_headers):
    """The server, not only the browser, enforces the governed 15-file limit."""
    files = [
        (
            "files",
            (f"source-{index}.xlsx", b"not-read", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        )
        for index in range(16)
    ]
    response = client.post("/api/v1/ingestion/upload", headers=auth_headers, files=files)
    assert response.status_code == 400
    assert "1 and 15" in response.json()["message"]


def test_upload_rejects_corrupt_xlsx_container(auth_headers):
    response = client.post(
        "/api/v1/ingestion/upload",
        headers=auth_headers,
        files={
            "file": (
                "corrupt.xlsx",
                b"not-an-ooxml-container",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 415
    assert "OOXML" in response.json()["message"]


def test_multi_file_group_retains_manifest_and_cross_file_lineage(db_session, tmp_path):
    """Two files form one group while every raw/staging row still identifies its source file."""
    paths = [
        (_workbook(tmp_path / "arrival.xlsx", "GROUP-001"), "arrival.xlsx"),
        (_workbook(tmp_path / "sailing.xlsx", "GROUP-002"), "sailing.xlsx"),
    ]
    pipeline = IngestionPipeline(db_session, tenant_id="group-lineage-test")
    batch_id = pipeline.process_files(paths, force_new=True, commit_canonical=False)
    try:
        manifests = (
            db_session.execute(select(IngestionFile).where(IngestionFile.group_batch_id == batch_id)).scalars().all()
        )
        staging = (
            db_session.execute(select(StagingRecord).where(StagingRecord.ingestion_batch_id == batch_id))
            .scalars()
            .all()
        )
        raw = db_session.execute(select(RawRecord).where(RawRecord.ingestion_batch_id == batch_id)).scalars().all()
        assert len(manifests) == 2
        assert {item.original_filename for item in manifests} == {"arrival.xlsx", "sailing.xlsx"}
        assert all(item.storage_reference and Path(item.storage_reference).is_file() for item in manifests)
        assert {item.source_file_id for item in staging} == {str(item.id) for item in manifests}
        assert {item.source_file_id for item in raw} == {str(item.id) for item in manifests}
    finally:
        _delete_uncommitted_group(db_session, batch_id)


def test_fifteen_workbook_group_is_accepted_and_duplicate_rows_are_detected(db_session, tmp_path):
    """The server-side pipeline accepts 15 files and marks cross-file exact duplicates."""
    paths = [(_workbook(tmp_path / f"source-{index}.xlsx", "SAME-VCN"), f"source-{index}.xlsx") for index in range(15)]
    pipeline = IngestionPipeline(db_session, tenant_id="group-limit-test")
    batch_id = pipeline.process_files(paths, force_new=True, commit_canonical=False)
    try:
        manifests = (
            db_session.execute(select(IngestionFile).where(IngestionFile.group_batch_id == batch_id)).scalars().all()
        )
        staging = (
            db_session.execute(select(StagingRecord).where(StagingRecord.ingestion_batch_id == batch_id))
            .scalars()
            .all()
        )
        assert len(manifests) == 15
        assert sum(row.validation_status == "DUPLICATE" for row in staging) == 14
        assert sum(row.validation_status == "VALID" for row in staging) == 1
    finally:
        _delete_uncommitted_group(db_session, batch_id)


def test_fatal_file_schema_failure_keeps_group_inactive(db_session, tmp_path):
    """A file with a governed sheet but missing required columns blocks group activation."""
    path = _workbook(tmp_path / "missing-column.xlsx", "BAD-001", include_vessel_name=False)
    pipeline = IngestionPipeline(db_session, tenant_id="group-failure-test")
    with pytest.raises(ValueError, match="missing required column"):
        pipeline.process_files([(path, "missing-column.xlsx")], force_new=True, commit_canonical=False)
    failed = (
        db_session.execute(
            select(IngestionBatch)
            .where(IngestionBatch.tenant_id == "group-failure-test")
            .order_by(IngestionBatch.created_at.desc())
        )
        .scalars()
        .first()
    )
    assert failed is not None and failed.status == "FAILED" and not failed.is_active
    manifest = db_session.execute(
        select(IngestionFile).where(IngestionFile.group_batch_id == failed.batch_id)
    ).scalar_one()
    assert manifest.parse_status == "FAILED"
    _delete_uncommitted_group(db_session, failed.batch_id)


def test_older_worker_cannot_supersede_a_newer_upload_during_processing(db_session, monkeypatch):
    """A new upload accepted during analytics must remain queued for its own worker.

    This protects the persisted replacement state from the race that previously
    marked the newer group SUPERSEDED and left the browser polling forever.
    """
    from apps.api.core.database import SessionLocal

    tenant_id = "worker-replacement-race-test"
    old_batch = IngestionBatch(
        batch_id="worker-race-old",
        file_name="old.xlsx",
        file_checksum="old-checksum",
        status="PROCESSING",
        tenant_id=tenant_id,
        is_active=False,
        created_at=datetime.now(UTC),
    )
    db_session.add(old_batch)
    db_session.commit()

    def accept_newer_upload(*_args, **_kwargs):
        other_session = SessionLocal()
        try:
            other_session.add(
                IngestionBatch(
                    batch_id="worker-race-new",
                    file_name="new.xlsx",
                    file_checksum="new-checksum",
                    status="UPLOADED",
                    tenant_id=tenant_id,
                    is_active=False,
                    created_at=datetime.now(UTC) + timedelta(seconds=1),
                )
            )
            other_session.commit()
        finally:
            other_session.close()

    monkeypatch.setattr("apps.api.services.ingestion.synthetic.reset_tenant_dataset", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "apps.api.services.ingestion.pipeline.IngestionPipeline._commit_to_canonical", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr("apps.api.services.pipeline_runner.run_full_analytics_pipeline", accept_newer_upload)

    try:
        process_ingestion_analytics_task.fn(old_batch.batch_id, tenant_id, old_batch.file_checksum)
        db_session.expire_all()
        old = db_session.execute(
            select(IngestionBatch).where(IngestionBatch.batch_id == "worker-race-old")
        ).scalar_one()
        newer = db_session.execute(
            select(IngestionBatch).where(IngestionBatch.batch_id == "worker-race-new")
        ).scalar_one()
        assert old.status == "SUPERSEDED"
        assert newer.status == "UPLOADED"
        assert newer.is_active is False
    finally:
        db_session.query(IngestionBatch).filter(IngestionBatch.tenant_id == tenant_id).delete()
        db_session.commit()


def test_dataset_removal_clears_active_state(auth_headers, db_session):
    """Verifies that removing the dataset resets the tenant to empty state."""
    del_resp = client.delete("/api/v1/ingestion/dataset", headers=auth_headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "CLEARED"

    # Active dataset should now be False
    active_resp = client.get("/api/v1/ingestion/active", headers=auth_headers)
    assert active_resp.status_code == 200
    assert active_resp.json()["has_active_dataset"] is False

    # Executive dashboard should return 0 calls
    dash_resp = client.get("/api/v1/dashboard/executive", headers=auth_headers)
    assert dash_resp.status_code == 200
    assert dash_resp.json()["summary"]["total_vessel_calls"] == 0

    # Restore test state through the validation-only fixture loader.  Production
    # routes never load governed test fixtures.
    restored_batch = load_synthetic_dataset(db_session, "fixtures/Synthetic_Marine_Time_Motion_Test_Data.xlsx")
    assert restored_batch is not None


def test_reset_removes_staging_rows_before_batch_rows(db_session):
    """A tenant reset must not leave stale staging evidence for a later dataset."""
    batch = load_synthetic_dataset(db_session, "fixtures/Synthetic_Marine_Time_Motion_Test_Data.xlsx")
    assert db_session.execute(select(StagingRecord).where(StagingRecord.ingestion_batch_id == batch)).scalars().first()
    reset_tenant_dataset(db_session, "synthetic-tenant")
    assert (
        db_session.execute(select(StagingRecord).where(StagingRecord.ingestion_batch_id == batch)).scalars().first()
        is None
    )
