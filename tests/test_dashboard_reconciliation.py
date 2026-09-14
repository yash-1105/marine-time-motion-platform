"""Automated 3-Way Reconciliation Test (spec §20.13, §21A.5.10, Phase 12).

Asserts that under identical filters:
1. Dashboard Total (GET /api/v1/dashboard/executive)
2. Analytics API Total (GET /api/v1/operations/vessel-calls)
3. Database Direct Total (canonical.vessel_call SQL query)
agree unconditionally.
Also asserts throughput unit segmentation and early service preservation.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from apps.api.auth.scope import DataScope
from apps.api.core.config import settings
from apps.api.main import app
from apps.api.models.canonical import VesselCall
from apps.api.repository.vessel_call import VesselCallRepository
from apps.api.services.dashboard.executive import ExecutiveDashboardService

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


def test_executive_dashboard_payload_structure(auth_headers):
    """Verifies the executive dashboard returns complete, governed operational data."""
    resp = client.get("/api/v1/dashboard/executive", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    # Summary
    assert data["summary"]["total_vessel_calls"] == 72
    assert data["summary"]["clean_calls_count"] > 0
    assert data["summary"]["quarantined_calls_count"] >= 1
    assert data["summary"]["cleanliness_pct"] > 0

    # Throughput strictly segmented (spec §12.1)
    tp = data["throughput"]
    assert tp["units_segmented"] is True
    assert tp["teu"] > 0
    assert tp["mt"] > 0
    assert tp["units"] > 0
    assert "prohibited_sum_notice" in tp

    # Lead Times (all 8 target metrics present)
    lt = data["lead_time_metrics"]
    for m in [
        "Turnaround",
        "Anchorage Wait",
        "Inward Movement",
        "Berth Stay",
        "Cargo Working",
        "Outward Movement",
        "Arrival Execution Delay",
        "Sailing Execution Delay",
    ]:
        assert m in lt
        assert lt[m]["status"] == "COMPUTED"
        assert lt[m]["observation_count"] > 0

    # Early service preservation (negative delays)
    assert lt["Arrival Execution Delay"]["early_service_count"] == 7
    assert lt["Sailing Execution Delay"]["early_service_count"] == 10

    # Delays & Bottlenecks
    d_sum = data["delays_summary"]
    assert d_sum["total_delays_count"] == 41
    assert d_sum["confirmed_count"] == 41
    assert len(d_sum["top_bottlenecks"]) > 0
    # Components exposed
    first_b = d_sum["top_bottlenecks"][0]
    assert "overall_bottleneck_score" in first_b
    assert "duration_score" in first_b
    assert "variability_score" in first_b
    assert "tail_risk_score" in first_b

    # Governed KPI Highlights
    kpi_hl = data["kpi_highlights"]
    assert len(kpi_hl) >= 6
    for k in kpi_hl:
        assert k["status"] == "COMPUTED"
        assert k["unit"] is not None

    # Lineage disclosure
    assert data["lineage"]["dataset_type"] == "HISTORICAL_SYNTHETIC"


def test_three_way_reconciliation_endpoint(auth_headers):
    """Executes the governed 3-way reconciliation endpoint asserting agreement across all test combinations."""
    resp = client.get("/api/v1/dashboard/reconciliation", headers=auth_headers)
    assert resp.status_code == 200
    report = resp.json()

    assert report["status"] == "PASS"
    assert report["all_combinations_reconciled"] is True
    assert report["total_combinations_tested"] >= 6

    for item in report["results"]:
        assert item["is_reconciled"] is True, f"Reconciliation failure in {item['combination_name']}"
        assert item["dashboard_total"] == item["analytics_api_total"] == item["database_direct_total"]


def test_direct_three_way_reconciliation_with_db(db_session, auth_headers):
    """Direct verification of Dashboard, Repository, and SQL query."""
    svc = ExecutiveDashboardService(db_session, tenant_id="synthetic-tenant")
    repo = VesselCallRepository(db_session)
    scope = DataScope(tenant_id="synthetic-tenant")

    combos = [
        ("All Calls", {}),
        ("Containerships", {"vessel_type": "Fully Cellular Containership"}),
        ("Bulk Carriers", {"vessel_type": "Bulk Carrier"}),
        ("Container Cargo", {"cargo_type": "Container"}),
        ("Bulk Cargo", {"cargo_type": "Bulk"}),
    ]

    for name, filters in combos:
        # 1. Dashboard Total
        dash_total = svc.get_executive_summary(**filters)["summary"]["total_vessel_calls"]

        # 2. Analytics Repository Total
        api_total = repo.count(scope=scope, is_merged=False, **filters)

        # 3. Direct SQL Total
        q = select(func.count(VesselCall.id)).where(
            VesselCall.is_merged == False,
            VesselCall.tenant_id == "synthetic-tenant",
        )
        if "vessel_type" in filters:
            q = q.where(VesselCall.vessel_type == filters["vessel_type"])
        if "cargo_type" in filters:
            q = q.where(VesselCall.cargo_type == filters["cargo_type"])
        db_total = db_session.execute(q).scalar()

        assert dash_total == api_total == db_total, (
            f"3-way reconciliation mismatch for {name}: "
            f"Dashboard={dash_total}, API={api_total}, DB={db_total}"
        )
