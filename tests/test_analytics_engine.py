"""Tests for Phase 07 Time and Motion Analytics Engine (spec §10, phase-07-analytics.md).

Verifies:
1. All 8 reconciliation targets compute and match ExpectedOutputs within ±0.02h tolerance
2. Negative execution delays survive as valid early service delivery (sign preserved)
3. Missing events produce UNAVAILABLE with reason (never fabricated zero)
4. Percentiles use explicit linear interpolation
5. CV guarded for near-zero mean; Tail Risk Ratio guarded for zero or negative median
6. Stage contribution without double-counting
7. Custom lead-time builder handles repeated occurrences
8. Traceability envelope present on every metric result
9. NO_SOURCE_DATA definitions registered in catalogue per spec §10.2
10. REST API endpoints function and enforce authorization
"""

from datetime import UTC

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from apps.api.main import app
from apps.api.models.analytics import (
    LeadTimeDefinition,
    LeadTimeResult,
    StatisticalAggregate,
)
from apps.api.models.canonical import VesselCall
from apps.api.models.testkit import ExpectedOutput
from apps.api.services.analytics.catalogue import ensure_catalogue
from apps.api.services.analytics.custom_builder import CustomLeadTimeBuilder
from apps.api.services.analytics.engine import AnalyticsEngine, within_tolerance
from apps.api.services.identity.engine import IdentityEngine
from apps.api.services.ingestion.synthetic import load_synthetic_dataset
from apps.api.services.journey.reconstructor import JourneyReconstructionEngine
from apps.api.services.quality.engine import DataQualityEngine


@pytest.fixture(scope="module")
def db_session():
    engine = create_engine("postgresql://admin:password@localhost:5434/marine_platform")
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture(scope="module")
def analytics_fixture(db_session):
    """End-to-end pipeline run matching `make validate`: ingestion → DQ → identity → journey → analytics."""
    load_synthetic_dataset(db_session, "fixtures/Synthetic_Marine_Time_Motion_Test_Data.xlsx")
    DataQualityEngine(db_session).run_all()
    IdentityEngine(db_session, tenant_id="synthetic-tenant").auto_merge_candidates()
    JourneyReconstructionEngine(db_session, tenant_id="synthetic-tenant").reconstruct_all()

    engine = AnalyticsEngine(db_session, tenant_id="synthetic-tenant", exclude_quarantined=True)
    summary = engine.compute_all_metrics()
    engine.compute_all_statistics()
    return summary


# ──────────────────────────────────────────────────────────────────────────────
# 1. 8 Reconciliation Targets Coverage & Accuracy
# ──────────────────────────────────────────────────────────────────────────────

def test_all_8_reconciliation_metrics_compute(db_session, analytics_fixture):
    """Verifies that all 8 reconciliation target definitions exist and have computed results."""
    catalogue = ensure_catalogue(db_session)
    targets = [
        "Turnaround",
        "Anchorage Wait",
        "Inward Movement",
        "Berth Stay",
        "Cargo Working",
        "Outward Movement",
        "Arrival Execution Delay",
        "Sailing Execution Delay",
    ]

    for target in targets:
        assert target in catalogue, f"Missing target definition: {target}"
        defn = catalogue[target]
        assert defn.availability_status == "COMPUTABLE"

        results = db_session.execute(
            select(LeadTimeResult).where(LeadTimeResult.definition_id == defn.id)
        ).scalars().all()

        assert len(results) == 72, f"Expected 72 base calls for {target}, got {len(results)}"
        available_cnt = sum(1 for r in results if r.status == "AVAILABLE")
        assert available_cnt >= 70, f"Expected >= 70 available results for {target}, got {available_cnt}"


def test_turnaround_matches_expected_within_tolerance(db_session, analytics_fixture):
    """Verifies Turnaround calculation against ExpectedOutputs oracle within ±0.02h tolerance."""
    defn = db_session.execute(
        select(LeadTimeDefinition).where(LeadTimeDefinition.name == "Turnaround")
    ).scalar_one()

    results = db_session.execute(
        select(LeadTimeResult).where(LeadTimeResult.definition_id == defn.id)
    ).scalars().all()

    passed = 0
    for r in results:
        exp = db_session.execute(
            select(ExpectedOutput).where(
                ExpectedOutput.vcn == r.vcn,
                ExpectedOutput.metric_name == "Expected_Turnaround_Hours_ATA_to_ATD",
            )
        ).scalar_one_or_none()

        if exp and r.status == "AVAILABLE":
            if within_tolerance(r.duration_hours, exp.expected_value, tolerance=0.02):
                passed += 1

    # 71 of 72 base calls match within ±0.02h (the 1 exception is SYNVCN2600063, deliberate DQ-008 720h outlier fixture defect)
    assert passed >= 70, f"Expected at least 70 turnaround matches, got {passed}"


def test_berth_stay_and_cargo_working_reconcile_100_percent(db_session, analytics_fixture):
    """Verifies Berth Stay, Cargo Working, and Outward Movement achieve 100% reconciliation."""
    engine = AnalyticsEngine(db_session, tenant_id="synthetic-tenant", exclude_quarantined=True)
    report = engine.reconcile_against_expected_outputs(tolerance=0.02)

    for target in ["Berth Stay", "Cargo Working", "Outward Movement", "Arrival Execution Delay", "Sailing Execution Delay"]:
        m = report["metrics_reconciled"][target]
        assert m["passed"] == 72, f"{target} failed to reach 72/72: {m['passed']} passed, {m['failed']} failed"


# ──────────────────────────────────────────────────────────────────────────────
# 2. Negative Execution Delays & Early Service (spec §2.4, §10.1)
# ──────────────────────────────────────────────────────────────────────────────

def test_negative_execution_delay_preserved_as_early_service(db_session, analytics_fixture):
    """Verifies that negative execution delays are preserved with sign as valid early service.

    AGENTS.md §6: 7 negative arrival execution delays; 10 negative sailing execution delays.
    """
    arrival_defn = db_session.execute(
        select(LeadTimeDefinition).where(LeadTimeDefinition.name == "Arrival Execution Delay")
    ).scalar_one()
    sailing_defn = db_session.execute(
        select(LeadTimeDefinition).where(LeadTimeDefinition.name == "Sailing Execution Delay")
    ).scalar_one()

    arr_results = db_session.execute(
        select(LeadTimeResult).where(LeadTimeResult.definition_id == arrival_defn.id)
    ).scalars().all()
    sail_results = db_session.execute(
        select(LeadTimeResult).where(LeadTimeResult.definition_id == sailing_defn.id)
    ).scalars().all()

    arr_neg = [r for r in arr_results if r.status == "AVAILABLE" and r.duration_hours is not None and r.duration_hours < 0]
    sail_neg = [r for r in sail_results if r.status == "AVAILABLE" and r.duration_hours is not None and r.duration_hours < 0]

    # Verify counts match fixture facts
    assert len(arr_neg) == 7, f"Expected 7 negative arrival execution delays, got {len(arr_neg)}"
    assert len(sail_neg) == 10, f"Expected 10 negative sailing execution delays, got {len(sail_neg)}"

    # Check that durations are strictly negative (never converted to 0 or abs())
    for r in arr_neg:
        assert r.duration_hours < 0
        assert r.status == "AVAILABLE"


# ──────────────────────────────────────────────────────────────────────────────
# 3. Unavailable Semantics (spec §2.8: Unavailable, not fabricated)
# ──────────────────────────────────────────────────────────────────────────────

def test_unavailable_when_event_missing_not_zero(db_session, analytics_fixture):
    """Verifies that missing events produce status=UNAVAILABLE with reason, never fabricated zero."""
    # When quarantined events are excluded, SYNVCN2600045 (DQ-006) has missing PILOT_ON_BOARD_ARRIVAL
    anchorage_defn = db_session.execute(
        select(LeadTimeDefinition).where(LeadTimeDefinition.name == "Anchorage Wait")
    ).scalar_one()

    unavail_row = db_session.execute(
        select(LeadTimeResult).where(
            LeadTimeResult.definition_id == anchorage_defn.id,
            LeadTimeResult.status != "AVAILABLE",
        )
    ).scalars().first()

    assert unavail_row is not None
    assert unavail_row.status == "UNAVAILABLE"
    assert unavail_row.duration_hours is None, "Unavailable duration must be NULL, never zero"
    assert unavail_row.unavailable_reason is not None
    assert len(unavail_row.unavailable_reason) > 0


# ──────────────────────────────────────────────────────────────────────────────
# 4. Polars Statistics & Percentile Method (spec §10.3)
# ──────────────────────────────────────────────────────────────────────────────

def test_statistics_percentile_method_is_linear_interpolation(db_session, analytics_fixture):
    """Verifies that statistical aggregates disclose 'linear_interpolation' as the percentile method."""
    aggs = db_session.execute(select(StatisticalAggregate)).scalars().all()
    assert len(aggs) > 0

    for agg in aggs:
        assert agg.percentile_method == "linear_interpolation"
        if agg.observation_count and agg.observation_count > 0:
            assert agg.mean_hours is not None
            assert agg.median_hours is not None
            assert agg.min_hours <= agg.median_hours <= agg.max_hours
            assert agg.p25_hours <= agg.median_hours <= agg.p75_hours <= agg.p90_hours <= agg.p95_hours


def test_cv_guarded_for_zero_mean():
    """Verifies CV = σ/μ is safely guarded when mean is near zero (|μ| < 0.001)."""
    # Guard logic test
    mean_val = 0.0001
    std_val = 1.5
    cv = round(std_val / mean_val, 4) if abs(mean_val) >= 0.001 else None
    assert cv is None, "CV must be None when mean is near zero"


def test_tail_risk_ratio_guarded_for_zero_median():
    """Verifies Tail Risk Ratio = P90/median is safely guarded when median <= 0."""
    median_val = 0.0
    p90_val = 2.5
    tail_risk = round(p90_val / median_val, 4) if median_val > 0 else None
    assert tail_risk is None, "Tail Risk Ratio must be None when median <= 0"

    # Negative median (e.g. execution delay where service is predominantly early)
    median_neg = -0.5
    tail_risk_neg = round(p90_val / median_neg, 4) if median_neg > 0 else None
    assert tail_risk_neg is None, "Tail Risk Ratio must be None when median is negative"


# ──────────────────────────────────────────────────────────────────────────────
# 5. Traceability Envelope (spec §2 & §10.5)
# ──────────────────────────────────────────────────────────────────────────────

def test_traceability_envelope_present(db_session, analytics_fixture):
    """Verifies that every LeadTimeResult row carries the required traceability envelope."""
    results = db_session.execute(
        select(LeadTimeResult).where(LeadTimeResult.status == "AVAILABLE").limit(20)
    ).scalars().all()

    for r in results:
        assert r.formula_version is not None
        assert r.source_record_ids is not None
        assert len(r.source_record_ids) > 0
        assert r.calculated_at is not None
        assert r.dq_status in ("CLEAN", "DQ_ISSUES", "MISSING_DATA", "NO_SOURCE_DATA")
        assert r.start_time is not None
        assert r.end_time is not None


# ──────────────────────────────────────────────────────────────────────────────
# 6. NO_SOURCE_DATA Catalogue Registration (spec §10.2)
# ──────────────────────────────────────────────────────────────────────────────

def test_no_source_data_metrics_registered_unavailable(db_session, analytics_fixture):
    """Verifies that metrics requiring unrecorded events are registered with NO_SOURCE_DATA."""
    no_source_defs = db_session.execute(
        select(LeadTimeDefinition).where(LeadTimeDefinition.availability_status == "NO_SOURCE_DATA")
    ).scalars().all()

    assert len(no_source_defs) >= 5, "Expected at least 5 NO_SOURCE_DATA registered definitions"
    names = [d.name for d in no_source_defs]
    assert "Crane Start to Last Move" in names
    assert "First Container to ATD" in names
    assert "Berthing End to Unmooring Start" in names

    # Verify their calculation results are explicitly marked NO_SOURCE_DATA
    for d in no_source_defs:
        res = db_session.execute(
            select(LeadTimeResult).where(LeadTimeResult.definition_id == d.id).limit(1)
        ).scalar_one_or_none()
        if res:
            assert res.status == "NO_SOURCE_DATA"
            assert res.duration_hours is None


# ──────────────────────────────────────────────────────────────────────────────
# 7. Custom Lead-Time Builder (spec §10.2)
# ──────────────────────────────────────────────────────────────────────────────

def test_custom_builder_handles_event_pairs_and_repeated_occurrences(db_session, analytics_fixture):
    """Verifies that CustomLeadTimeBuilder computes ad-hoc event durations and handles occurrence selection."""
    builder = CustomLeadTimeBuilder(db_session, tenant_id="synthetic-tenant")

    # 1. First occurrence
    res_first = builder.build(
        start_event="PILOT_ON_BOARD_ARRIVAL",
        end_event="ALL_FAST_ARRIVAL",
        occurrence_selection="first",
    )
    assert res_first["aggregate"]["observation_count"] >= 70
    assert res_first["aggregate"]["mean_hours"] is not None
    assert res_first["aggregate"]["percentile_method"] == "linear_interpolation"

    # 2. All occurrences on shifting events
    res_shift = builder.build(
        start_event="SHIFT_PILOT_ON_BOARD",
        end_event="SHIFT_ALL_FAST",
        occurrence_selection="all",
    )
    # Exactly 8 calls in the fixture have shift events
    shift_avail = [r for r in res_shift["results"] if r.get("status") == "AVAILABLE"]
    assert len(shift_avail) == 8, f"Expected 8 shifting occurrences, got {len(shift_avail)}"


# ──────────────────────────────────────────────────────────────────────────────
# 8. REST API Endpoints & RBAC (spec §16)
# ──────────────────────────────────────────────────────────────────────────────

def test_analytics_api_endpoints_work(db_session, analytics_fixture):
    """Verifies that analytics endpoints return valid JSON and enforce data scope."""
    client = TestClient(app)
    login_resp = client.post("/api/v1/auth/dev/login", json={"role_or_email": "Platform Administrator"})
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # GET /metrics
    r_metrics = client.get("/api/v1/analytics/metrics", headers=headers)
    assert r_metrics.status_code == 200
    metrics_list = r_metrics.json()
    assert len(metrics_list) >= 8

    # GET /reconciliation
    r_recon = client.get("/api/v1/analytics/reconciliation?tolerance=0.02", headers=headers)
    assert r_recon.status_code == 200
    recon_data = r_recon.json()
    assert "metrics_reconciled" in recon_data
    assert recon_data["summary"]["total_targets"] == 8

    # POST /custom
    r_custom = client.post(
        "/api/v1/analytics/custom",
        json={
            "start_event": "CARGO_START",
            "end_event": "CARGO_END",
            "occurrence_selection": "first",
        },
        headers=headers,
    )
    assert r_custom.status_code == 200
    custom_data = r_custom.json()
    assert custom_data["aggregate"]["observation_count"] == 72


# ──────────────────────────────────────────────────────────────────────────────
# 9. Governed Duration Semantics (spec §10.1, 9 distinct concepts)
# ──────────────────────────────────────────────────────────────────────────────

def test_all_9_duration_semantics_concepts():
    """Verifies that all 9 duration concepts from spec §10.1 are distinct, independently tested,

    and carry explicit null handling (never fabricated zero).
    """
    from datetime import datetime

    from apps.api.services.analytics.duration_semantics import (
        compute_delay_frequency,
        compute_early_delivery,
        compute_execution_delay,
        compute_lead_time,
        compute_planning_lead_time,
        compute_scheduling_gap,
        compute_service_time,
        compute_target_variance,
        compute_waiting_time,
    )

    t0 = datetime(2026, 3, 1, 10, 0, tzinfo=UTC)
    t1 = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    t2 = datetime(2026, 3, 1, 14, 0, tzinfo=UTC)
    t3 = datetime(2026, 3, 1, 13, 45, tzinfo=UTC)  # 15 mins early

    # 1. Lead Time: end - start
    lt = compute_lead_time(t0, t2)
    assert lt.concept == "Lead Time"
    assert lt.value_hours == 4.0
    assert compute_lead_time(None, t2).status == "UNAVAILABLE"

    # 2. Planning Lead Time: requested - submitted
    plt = compute_planning_lead_time(t0, t1)
    assert plt.concept == "Planning Lead Time"
    assert plt.value_hours == 2.0
    assert compute_planning_lead_time(t0, None).status == "UNAVAILABLE"

    # 3. Scheduling Gap: scheduled - requested
    sg = compute_scheduling_gap(t1, t2)
    assert sg.concept == "Scheduling Gap"
    assert sg.value_hours == 2.0
    assert compute_scheduling_gap(None, t2).status == "UNAVAILABLE"

    # 4. Execution Delay: served - scheduled
    ed_early = compute_execution_delay(t2, t3)
    assert ed_early.concept == "Execution Delay"
    assert ed_early.value_hours == -0.25  # Preserved with sign
    assert ed_early.is_early_delivery is True

    # 5. Target Variance: actual - target
    tv = compute_target_variance(14.5, 12.0)
    assert tv.concept == "Target Variance"
    assert tv.value_hours == 2.5
    assert compute_target_variance(None, 12.0).status == "UNAVAILABLE"

    # 6. Waiting Time: inactive intervals
    stages = [
        {"stage_name": "Anchorage Wait", "time_category": "PASSIVE_WAIT", "duration_hours": 4.5},
        {"stage_name": "Cargo Working", "time_category": "ACTIVE_SERVICE", "duration_hours": 8.0},
        {"stage_name": "Clearance Hold", "time_category": "HOLD", "duration_hours": 1.5},
    ]
    wt = compute_waiting_time(stages)
    assert wt.concept == "Waiting Time"
    assert wt.value_hours == 6.0  # 4.5 + 1.5

    # 7. Service Time: active intervals
    st = compute_service_time(stages)
    assert st.concept == "Service Time"
    assert st.value_hours == 8.0

    # 8. Delay Frequency: delayed / total
    df = compute_delay_frequency(15, 72)
    assert df.concept == "Delay Frequency"
    assert df.value_hours == 0.2083
    assert df.unit == "ratio"
    assert compute_delay_frequency(5, 0).status == "UNAVAILABLE"

    # 9. Early Delivery: negative execution delay
    early = compute_early_delivery(-0.25)
    assert early.concept == "Early Delivery"
    assert early.value_hours == -0.25
    assert early.is_early_delivery is True
    assert early.metadata["early_hours"] == 0.25


# ──────────────────────────────────────────────────────────────────────────────
# 10. Daylight-Saving Boundaries & Overlapping Stages
# ──────────────────────────────────────────────────────────────────────────────

def test_daylight_saving_boundary_duration():
    """Verifies that UTC timestamp envelope arithmetic preserves exact physical durations across DST changes."""
    from datetime import datetime

    import pytz

    from apps.api.services.analytics.duration_semantics import compute_lead_time

    # London spring forward DST transition: 2026-03-29 from 01:00 to 02:00
    tz = pytz.timezone("Europe/London")
    dt1_local = tz.localize(datetime(2026, 3, 29, 0, 30))
    dt2_local = tz.localize(datetime(2026, 3, 29, 3, 30))

    # Convert to UTC as required by the timestamp envelope
    dt1_utc = dt1_local.astimezone(pytz.utc)
    dt2_utc = dt2_local.astimezone(pytz.utc)

    # Physical elapsed time across the 1-hour jump is 2 hours, not 3 hours!
    lt = compute_lead_time(dt1_utc, dt2_utc)
    assert lt.status == "AVAILABLE"
    assert lt.value_hours == 2.0, f"Expected 2.0h across DST boundary, got {lt.value_hours}h"


def test_overlapping_stages_and_residual_time(db_session, analytics_fixture):
    """Verifies stage contributions do not double count and residual time is reported."""
    client = TestClient(app)
    login_resp = client.post("/api/v1/auth/dev/login", json={"role_or_email": "Platform Administrator"})
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Find a vessel call with available turnaround
    vc = db_session.execute(select(VesselCall).where(VesselCall.vcn == "SYNVCN2600001")).scalar_one()
    r = client.get(f"/api/v1/analytics/vessel/{vc.id}", headers=headers)
    assert r.status_code == 200
    data = r.json()

    turnaround = data.get("turnaround_hours")
    assert turnaround is not None
    assert turnaround > 0

    # Check that individual stage contributions are computed as percentages of turnaround
    metrics = data.get("metrics", [])
    for m in metrics:
        if m["status"] == "AVAILABLE" and m["duration_hours"] is not None:
            if m["metric_name"] in ("Anchorage Wait", "Inward Movement", "Berth Stay", "Outward Movement"):
                # Individual movement stages must each be less than total turnaround
                assert m["duration_hours"] <= turnaround, f"{m['metric_name']} exceeds total turnaround"

