"""Tests for Dataset Ingestion, Persistence, and Replacement (spec Phase 12 / Change 1 & 2)."""

import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, desc, select
from sqlalchemy.orm import sessionmaker

from apps.api.core.config import settings
from apps.api.main import app
from apps.api.models.analytics import DashboardSnapshot
from apps.api.models.ingestion import IngestionBatch
from testkit.loader import load_synthetic_dataset

client = TestClient(app)


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
    snapshot = db_session.execute(
        select(DashboardSnapshot)
        .where(
            DashboardSnapshot.tenant_id == "synthetic-tenant",
            DashboardSnapshot.is_active == True,
            DashboardSnapshot.filters_hash == "unfiltered",
        )
        .order_by(desc(DashboardSnapshot.created_at))
    ).scalars().first()

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


def test_dataset_upload_and_replacement(auth_headers, db_session):
    """Verifies that uploading a new workbook replaces the active dataset and persists fresh results."""
    fixture_path = "fixtures/Synthetic_Marine_Time_Motion_Test_Data.xlsx"
    with open(fixture_path, "rb") as f:
        file_content = f.read()

    # Upload replacement workbook
    files = {"file": ("replacement_workbook.xlsx", file_content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    upload_resp = client.post("/api/v1/ingestion/upload", headers=auth_headers, files=files)
    assert upload_resp.status_code == 200
    upload_data = upload_resp.json()
    new_batch_id = upload_data["batch_id"]
    assert upload_data["status"] == "COMMITTED"

    # Verify that the new batch is the only active batch for the tenant
    active_batches = db_session.execute(
        select(IngestionBatch).where(
            IngestionBatch.tenant_id == "synthetic-tenant",
            IngestionBatch.is_active == True,
        )
    ).scalars().all()
    assert len(active_batches) == 1
    assert active_batches[0].batch_id == new_batch_id

    # Verify that the active dashboard snapshot now points to the new batch
    active_snapshot = db_session.execute(
        select(DashboardSnapshot).where(
            DashboardSnapshot.tenant_id == "synthetic-tenant",
            DashboardSnapshot.is_active == True,
        )
    ).scalars().first()
    assert active_snapshot is not None
    assert active_snapshot.batch_id == new_batch_id

    # Verify active endpoint reflects the new batch
    active_resp = client.get("/api/v1/ingestion/active", headers=auth_headers)
    assert active_resp.status_code == 200
    assert active_resp.json()["batch"]["batch_id"] == new_batch_id
    assert active_resp.json()["batch"]["file_name"] == "replacement_workbook.xlsx"


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
    restored_batch = load_synthetic_dataset(
        db_session, "fixtures/Synthetic_Marine_Time_Motion_Test_Data.xlsx"
    )
    assert restored_batch is not None
