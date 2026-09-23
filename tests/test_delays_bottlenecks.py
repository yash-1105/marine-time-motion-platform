"""Tests for Phase 09: Delay analysis, bottlenecks, outliers, criticality, and alerts."""
import pytest
from datetime import UTC, datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select

from apps.api.core.database import SessionLocal
from apps.api.main import app
from apps.api.models.analytics import ActionItem, OperationalAlert, OutlierRecord
from apps.api.models.canonical import Delay, DelayAllocation, ServiceAssignment, ServiceExecution, ServiceRequest, VesselCall
from apps.api.models.quality import QualityIssue, QualityRule
from apps.api.services.alerts.engine import AlertEngine
from apps.api.services.bottlenecks.engine import BottleneckEngine
from apps.api.services.criticality.engine import CriticalityEngine
from apps.api.services.delays.inference import DelayInferenceEngine
from apps.api.services.delays.mapping import CANONICAL_DELAY_CATEGORIES, map_to_canonical_category
from apps.api.services.delays.service import DelayService
from apps.api.services.outliers.engine import OutlierEngine
from apps.api.services.quality.engine import DataQualityEngine


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def auth_headers():
    client = TestClient(app)
    res = client.post("/api/v1/auth/dev/login", json={"role_or_email": "Platform Administrator"})
    assert res.status_code == 200, f"Login failed: {res.text}"
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_canonical_delay_categories_mapping():
    """Verify source categories and reasons map accurately into the 15 governed categories."""
    assert len(CANONICAL_DELAY_CATEGORIES) == 15
    assert "Pilot" in CANONICAL_DELAY_CATEGORIES
    assert "Tug" in CANONICAL_DELAY_CATEGORIES
    assert "Berth Non-Availability" in CANONICAL_DELAY_CATEGORIES
    assert "Weather" in CANONICAL_DELAY_CATEGORIES

    # Fixture source values test
    assert map_to_canonical_category("Weather", "High Swells") == "Weather"
    assert map_to_canonical_category("Vessel/Other", "Ship Not Ready") == "Vessel-Side"
    assert map_to_canonical_category("Marine Service", "Tug Occupied") == "Tug"
    assert map_to_canonical_category("Marine Service", "Tug Out of Service") == "Tug"
    assert map_to_canonical_category("Marine Service", "Pilot Delay") == "Pilot"
    assert map_to_canonical_category("Terminal", "Berth Unavailable") == "Berth Non-Availability"
    assert map_to_canonical_category("Terminal", "Terminal Awaiting Cargo") == "Terminal Readiness"
    assert map_to_canonical_category("Vessel/Other", "Documentation Delay") == "Documentation"
    assert map_to_canonical_category("Marine Service", "Change of Shift") == "Port-Side"


def test_service_timing_preserves_frd_delay_signs_and_legs(db):
    """Requested/scheduled/served metrics use FRD signs and never classify SHIFTING as arrival/sailing."""
    vc = db.execute(select(VesselCall).limit(1)).scalar_one()
    base = datetime(2026, 1, 1, 23, 50, tzinfo=UTC)
    created = []
    for movement, service_type, scheduled_offset, served_offset in [
        ("Arrival", "Pilotage Service", 15, 35),   # +15m schedule, +20m late execution
        ("Sailing", "Tug Service", 0, 0),           # on time
        ("Shifting", "Berthing Service", 15, 5),    # early service, separate leg
    ]:
        request = ServiceRequest(vessel_call_id=vc.id, service_type=service_type, movement_type=movement, submission_time=base, requested_time=base + timedelta(minutes=10))
        db.add(request); db.flush()
        assignment = ServiceAssignment(service_request_id=request.id, scheduled_time=base + timedelta(minutes=10 + scheduled_offset))
        db.add(assignment); db.flush()
        execution = ServiceExecution(service_assignment_id=assignment.id, served_time=base + timedelta(minutes=10 + served_offset))
        db.add(execution); created.extend([request, assignment, execution])
    db.commit()
    try:
        rows = DelayService(db, tenant_id=vc.tenant_id).list_service_timings()["items"]
        ours = [row for row in rows if row["service_request_id"] == str(created[0].id) or row["service_request_id"] == str(created[3].id) or row["service_request_id"] == str(created[6].id)]
        arrival = next(row for row in ours if row["leg"] == "ARRIVAL_INWARD")
        sailing = next(row for row in ours if row["leg"] == "SAILING_OUTWARD")
        shifting = next(row for row in ours if row["leg"] == "SHIFTING")
        assert arrival["planning_lead_time_hours"] == pytest.approx(1 / 6, abs=1e-6)
        assert arrival["scheduling_gap_hours"] == pytest.approx(1 / 4, abs=1e-6)
        assert arrival["execution_delay_hours"] == pytest.approx(1 / 3, abs=1e-6)
        assert arrival["execution_delay_status"] == "LATE"
        assert sailing["execution_delay_hours"] == 0
        assert sailing["execution_delay_status"] == "ON_TIME"
        assert shifting["execution_delay_hours"] == pytest.approx(-1 / 6, abs=1e-6)
        assert shifting["execution_delay_status"] == "EARLY"
        assert shifting["service_duration_hours"] is None
    finally:
        for item in [created[2], created[5], created[8]]:
            db.delete(item)
        db.flush()
        for item in [created[1], created[4], created[7]]:
            db.delete(item)
        db.flush()
        for item in [created[0], created[3], created[6]]:
            db.delete(item)
        db.commit()


def test_service_timing_missing_inputs_and_schedule_chronology_are_explicit(db):
    """Missing inputs remain unavailable, while schedule-before-request becomes a DQ issue."""
    vc = VesselCall(vessel_name="Delay timing test vessel", vcn="TEST-SERVICE-TIMING", tenant_id="tenant-synthetic-01")
    db.add(vc); db.flush()
    request = ServiceRequest(
        vessel_call_id=vc.id, service_type="Pilotage Service", movement_type="Arrival",
        submission_time=datetime(2026, 1, 1, 23, 55, tzinfo=UTC),
        requested_time=datetime(2026, 1, 2, 0, 10, tzinfo=UTC),
    )
    db.add(request); db.flush()
    assignment = ServiceAssignment(service_request_id=request.id, scheduled_time=datetime(2026, 1, 2, 0, 5, tzinfo=UTC))
    db.add(assignment); db.flush()
    execution = ServiceExecution(service_assignment_id=assignment.id, served_time=None)
    db.add(execution); db.commit()
    try:
        row = next(item for item in DelayService(db, tenant_id=vc.tenant_id).list_service_timings()["items"] if item["service_request_id"] == str(request.id))
        assert row["planning_lead_time_hours"] == pytest.approx(0.25)  # crosses midnight with timezone-aware values
        assert row["scheduling_gap_hours"] == pytest.approx(-1 / 12, abs=1e-6)
        assert row["execution_delay_hours"] is None
        assert row["execution_delay_status"] == "UNAVAILABLE"
        assert row["data_quality_status"] == "DQ_SCHEDULE_BEFORE_REQUEST"
        DataQualityEngine(db).evaluate_vessel_call(vc)
        db.commit()
        issue = db.execute(
            select(QualityIssue)
            .join(QualityRule, QualityIssue.rule_id == QualityRule.id)
            .where(QualityIssue.vessel_call_id == vc.id, QualityRule.rule_id == "DQ-SERVICE-SCHEDULE-BEFORE-REQUEST")
        ).scalar_one()
        assert issue.record_reference == f"ServiceAssignment:{assignment.id}"
    finally:
        for issue in db.execute(select(QualityIssue).where(QualityIssue.vessel_call_id == vc.id)).scalars().all():
            db.delete(issue)
        db.delete(execution); db.flush()
        db.delete(assignment); db.flush()
        db.delete(request); db.flush()
        db.delete(vc); db.commit()


def test_delay_allocation_and_unallocated_remainder(db):
    """
    Verify multiple causes per delay, primary/secondary designation,
    and unallocated remainder tracking.
    """
    vc = db.execute(select(VesselCall).limit(1)).scalar_one()
    delay = Delay(
        vessel_call_id=vc.id,
        source_delay_id="TEST-DL-001",
        movement_stage="Arrival",
        total_duration_hours=5.0,
        is_early_service=False,
        delay_hours=5.0,
        recalculated_delay_hours=5.0,
        delay_reason="Multiple compound issues",
        canonical_category="Port-Side",
        cause_status="Confirmed",
    )
    db.add(delay)
    db.commit()

    try:
        service = DelayService(db, tenant_id="test")

        # Allocate 3h to Weather (Primary) and 1h to Tug (Secondary). Remainder = 1.0h unallocated.
        updated = service.allocate_causes(
            delay_id=delay.id,
            allocations_data=[
                {"canonical_category": "Weather", "reason": "High swells at fairway", "duration_hours": 3.0, "is_primary": True},
                {"canonical_category": "Tug", "reason": "Tug dispatch delay", "duration_hours": 1.0, "is_primary": False},
            ],
            actor="test_analyst",
        )

        assert updated["allocated_duration_hours"] == 4.0
        assert updated["unallocated_duration_hours"] == 1.0
        assert len(updated["allocations"]) == 2
        assert updated["allocations"][0]["is_primary"] is True
        assert updated["allocations"][0]["canonical_category"] == "Weather"
        assert updated["allocations"][1]["is_primary"] is False
        assert updated["allocations"][1]["canonical_category"] == "Tug"

        # Allocations exceeding total duration must raise ValueError
        with pytest.raises(ValueError, match="exceeds delay total duration"):
            service.allocate_causes(
                delay_id=delay.id,
                allocations_data=[
                    {"canonical_category": "Weather", "reason": "High swells", "duration_hours": 4.0},
                    {"canonical_category": "Tug", "reason": "Tug delay", "duration_hours": 3.0},
                ],
            )
    finally:
        db.query(DelayAllocation).filter(DelayAllocation.delay_id == delay.id).delete()
        db.delete(delay)
        db.commit()


def test_confirmed_cause_preservation_and_inference_decline(db):
    """
    HARD RULE: Inferred causes never overwrite confirmed causes.
    The engine must demonstrably decline to overwrite a confirmed delay.
    """
    vc = db.execute(select(VesselCall).limit(1)).scalar_one()
    delay = Delay(
        vessel_call_id=vc.id,
        source_delay_id="TEST-DL-CONFIRMED",
        movement_stage="Arrival",
        total_duration_hours=2.0,
        is_early_service=False,
        delay_hours=2.0,
        recalculated_delay_hours=2.0,
        delay_reason="High Swells",
        canonical_category="Weather",
        cause_status="Confirmed",
        confidence="High",
    )
    db.add(delay)
    db.commit()

    try:
        engine = DelayInferenceEngine(db, tenant_id="test")
        res = engine.infer_delay_cause(delay_id=delay.id)

        # Must DECLINE to overwrite
        assert res["status"] == "DECLINED_CONFIRMED_PRESERVED"
        assert "never overwrite confirmed facts" in res["message"]

        # Delay state in DB remains untouched
        db.refresh(delay)
        assert delay.cause_status == "Confirmed"
        assert delay.delay_reason == "High Swells"
        assert delay.canonical_category == "Weather"
    finally:
        db.query(DelayAllocation).filter(DelayAllocation.delay_id == delay.id).delete()
        db.delete(delay)
        db.commit()


def test_inference_isolation_and_evidence(db):
    """
    Verify inference on an unassigned delay generates proposed cause,
    confidence score, supporting/opposing evidence, and review state PENDING_REVIEW.
    """
    vc = db.execute(select(VesselCall).limit(1)).scalar_one()
    delay = Delay(
        vessel_call_id=vc.id,
        source_delay_id="TEST-DL-INFER",
        movement_stage="Arrival",
        total_duration_hours=1.5,
        is_early_service=False,
        delay_hours=1.5,
        cause_status="Unconfirmed",
        requires_reason_review=True,
    )
    db.add(delay)
    db.commit()

    try:
        engine = DelayInferenceEngine(db, tenant_id="test")
        res = engine.infer_delay_cause(delay_id=delay.id)

        assert res["status"] == "INFERRED_SUCCESS"
        assert res["cause_status"] == "INFERRED"
        assert res["confidence"] > 0.0
        assert len(res["supporting_factors"]) > 0
        assert res["human_review_state"] == "PENDING_REVIEW"

        # Check allocation
        alloc = db.execute(select(DelayAllocation).where(DelayAllocation.delay_id == delay.id)).scalar_one()
        assert alloc.cause_status == "INFERRED"
        assert alloc.human_review_state == "PENDING_REVIEW"
        assert "[INFERRED]" in alloc.reason
    finally:
        db.query(DelayAllocation).filter(DelayAllocation.delay_id == delay.id).delete()
        db.delete(delay)
        db.commit()


def test_dq007_missing_delay_reason_review(db):
    """
    Verify DQ-007 (SYNVCN2600054, positive execution delay without documented reason):
    Raises mandatory delay-reason review and allows governed resolution.
    """
    # Look for SYNVCN2600054
    vc = db.execute(select(VesselCall).where(VesselCall.vcn == "SYNVCN2600054")).scalar_one_or_none()
    assert vc is not None, "SYNVCN2600054 must exist in canonical vessel calls"

    # Create positive delay with missing reason to simulate DQ-007 review queue
    delay = Delay(
        vessel_call_id=vc.id,
        source_delay_id="DQ-007-DL",
        movement_stage="Arrival",
        total_duration_hours=0.33,
        is_early_service=False,
        delay_hours=0.33,
        delay_reason=None,
        source_category=None,
        canonical_category="Other",
        requires_reason_review=True,
        resolution_status="Open",
    )
    db.add(delay)
    db.commit()

    try:
        service = DelayService(db, tenant_id="test")
        delays_res = service.list_delays(requires_review=True)
        assert any(d["id"] == str(delay.id) for d in delays_res["items"])

        # Steward reviews and assigns reason
        resolved = service.review_delay_reason(
            delay_id=delay.id,
            canonical_category="Pilot",
            reason="Pilot delayed due to harbor traffic congestion",
            actor="lead_analyst",
            decision="APPROVED",
            notes="Remediated DQ-007 missing delay reason",
        )

        assert resolved["requires_reason_review"] is False
        assert resolved["resolution_status"] == "Closed"
        assert resolved["canonical_category"] == "Pilot"
        assert resolved["delay_reason"] == "Pilot delayed due to harbor traffic congestion"
    finally:
        db.query(DelayAllocation).filter(DelayAllocation.delay_id == delay.id).delete()
        db.delete(delay)
        db.commit()


def test_operational_outlier_is_evidenced_and_exclusion_is_governed(db):
    """
    Production outliers derive from governed observed data, never a fixture oracle;
    each persisted outlier supports a transparent steward exclusion decision.
    """
    outlier_engine = OutlierEngine(db, tenant_id="test")
    outliers = outlier_engine.detect_all_outliers(persist=True)

    assert outliers, "The governed outlier rules should identify observed anomalies"
    case = outliers[0]
    assert case["observed_value"] is not None
    assert case["outlier_type"] in ["DATA_QUALITY_OUTLIER", "OPERATIONAL_OUTLIER", "EXTREME_DELAY_CASE", "PROCESS_VIOLATION"]

    # Toggle exclusion
    outlier_rec = db.execute(select(OutlierRecord).where(OutlierRecord.vcn == case["vcn"], OutlierRecord.metric_name == case["metric_name"])).first()[0]
    toggled = outlier_engine.toggle_outlier_exclusion(
        outlier_id=outlier_rec.id,
        is_excluded=True,
        rationale="Observed anomaly excluded after documented steward review",
        actor="lead_steward",
    )
    assert toggled["is_excluded_from_kpi"] is True
    assert "documented steward" in toggled["exclusion_rationale"]


def test_non_duration_only_bottleneck_ranking():
    """
    HARD REQUIREMENT: Never label the longest stage alone as the bottleneck.
    Asserts that a long-but-stable stage (e.g. Berth Stay with low CV and zero breaches)
    ranks LOWER than a shorter-but-highly-variable stage with severe tail risk and high breaches.
    """
    engine = BottleneckEngine(db=None)

    # Case A: Long stage, but highly stable and predictable (e.g. Berth Stay: mean 40h, CV 0.05, TRR 1.1, 0% breach)
    # Case B: Shorter stage, but wildly variable and unpredictable (e.g. Anchorage Wait: mean 5h, CV 1.4, TRR 4.0, 75% breach)
    scores_long_stable = engine._compute_metrics_and_scores(
        values=[38.0, 39.0, 40.0, 41.0, 42.0],
        target_threshold=48.0,
        biz_crit=3.0,
        mean_turnaround=50.0,
        is_delay=False,
    )
    scores_short_variable = engine._compute_metrics_and_scores(
        values=[1.0, 1.2, 1.5, 4.0, 17.3],
        target_threshold=2.0,
        biz_crit=4.5,
        mean_turnaround=50.0,
        is_delay=False,
    )

    # Check components
    assert scores_long_stable["mean_hours"] == 40.0
    assert scores_short_variable["mean_hours"] == 5.0
    assert scores_long_stable["mean_hours"] > scores_short_variable["mean_hours"] * 7

    # But variability and tail risk are much worse for short_variable
    assert scores_short_variable["variability_score"] > scores_long_stable["variability_score"]
    assert scores_short_variable["tail_risk_score"] > scores_long_stable["tail_risk_score"]
    assert scores_short_variable["target_breach_score"] > scores_long_stable["target_breach_score"]

    # Calculate overall weighted bottleneck score
    w = {"duration": 0.15, "frequency": 0.20, "variability": 0.20, "tail_risk": 0.20, "turnaround_contribution": 0.10, "repeated_target_breach": 0.15}
    tot_w = sum(w.values())
    nw = {k: v / tot_w for k, v in w.items()}

    key_map = {
        "duration": "duration_score",
        "frequency": "frequency_score",
        "variability": "variability_score",
        "tail_risk": "tail_risk_score",
        "turnaround_contribution": "turnaround_contribution_score",
        "repeated_target_breach": "target_breach_score",
    }
    overall_long_stable = sum(nw[k] * scores_long_stable[key_map[k]] for k in nw)
    overall_short_variable = sum(nw[k] * scores_short_variable[key_map[k]] for k in nw)

    # The short-but-variable stage MUST rank higher than the long-but-stable stage!
    assert overall_short_variable > overall_long_stable, (
        f"Expected short-variable ({overall_short_variable}) to rank higher than long-stable ({overall_long_stable})"
    )


def test_criticality_three_component_scores_always_exposed():
    """
    HARD RULE: Always display the three component scores alongside overall score.
    No black-box score anywhere.
    """
    crit_engine = CriticalityEngine(db=None)

    # Test duration=1.0h, cv=1.3 (high), tail_risk_ratio=3.8 (high)
    res = crit_engine.compute_component_scores(
        duration_hours=1.0,
        cv=1.3,
        tail_risk_ratio=3.8,
    )

    # All three component scores must be present and discrete numbers 1 to 5
    assert "duration_score" in res
    assert "variability_score" in res
    assert "tail_risk_score" in res
    assert "overall_score" in res
    assert "band" in res

    assert res["duration_score"] == 1.0  # low duration
    assert res["variability_score"] == 5.0  # extreme variability
    assert res["tail_risk_score"] == 5.0  # extreme tail risk
    assert res["overall_score"] == pytest.approx((1.0 + 5.0 + 5.0) / 3.0, abs=0.02)
    assert res["band"] == "HIGH"


def test_alerts_lifecycle_acknowledge_and_resolve(db):
    """
    Verify alert generation, acknowledgement, and resolution workflow with audit logging.
    """
    alert_engine = AlertEngine(db, tenant_id="test")
    alert_engine.seed_default_rules()

    # Create test alert
    alert = OperationalAlert(
        rule_code="RULE_RESOURCE_SHORTAGE",
        severity="HIGH",
        title="Test Pilot Shortage Alert",
        description="High pilot dispatch delay",
        status="NEW",
        linked_entity_type="test",
        linked_entity_id="test-1",
    )
    db.add(alert)
    db.commit()

    try:
        # 1. Acknowledge
        ack = alert_engine.acknowledge_alert(alert.id, actor="duty_officer")
        assert ack["status"] == "ACKNOWLEDGED"
        assert ack["acknowledged_by"] == "duty_officer"

        # 2. Resolve
        res = alert_engine.resolve_alert(alert.id, resolution_notes="Second pilot boarded and operation normalized", actor="duty_officer")
        assert res["status"] == "RESOLVED"
        assert res["resolution_notes"] == "Second pilot boarded and operation normalized"

        # 3. Action item creation
        action = alert_engine.create_action_item(
            title="Review pilot shift handover protocol",
            description="Address recurrent delay during 06:00 shift change",
            assigned_to="harbour_master",
            priority="HIGH",
            alert_id=alert.id,
            created_by="duty_officer",
        )
        assert action["status"] == "OPEN"
        assert action["priority"] == "HIGH"
    finally:
        db.execute(select(ActionItem).where(ActionItem.alert_id == alert.id))
        db.query(ActionItem).filter(ActionItem.alert_id == alert.id).delete()
        db.delete(alert)
        db.commit()


def test_rest_api_endpoints_delays_and_bottlenecks(auth_headers):
    """Verify REST API routes return correct status and data shapes."""
    client = TestClient(app)

    # 1. Delays list
    res_delays = client.get("/api/v1/delays", headers=auth_headers)
    assert res_delays.status_code == 200
    data = res_delays.json()
    assert "total" in data
    assert "items" in data
    assert len(data["items"]) > 0

    # 2. Delays summary (Pareto)
    res_summary = client.get("/api/v1/delays/summary", headers=auth_headers)
    assert res_summary.status_code == 200
    summary = res_summary.json()
    assert "pareto_categories" in summary
    assert "total_delay_hours" in summary

    # 3. Bottlenecks
    res_bn = client.get("/api/v1/bottlenecks", headers=auth_headers)
    assert res_bn.status_code == 200
    bns = res_bn.json()
    assert len(bns) > 0
    assert "overall_bottleneck_score" in bns[0]
    assert "bottleneck_type" in bns[0]

    # 4. Outliers
    res_outliers = client.get("/api/v1/outliers", headers=auth_headers)
    assert res_outliers.status_code == 200
    outliers = res_outliers.json()
    assert all("vcn" in o and "evidence" in o for o in outliers)

    # 5. Criticality
    res_crit_eval = client.post(
        "/api/v1/criticality/evaluate",
        json={"duration_hours": 14.5, "cv": 0.65, "tail_risk_ratio": 2.2},
        headers=auth_headers,
    )
    assert res_crit_eval.status_code == 200
    crit = res_crit_eval.json()
    assert "duration_score" in crit
    assert "variability_score" in crit
    assert "tail_risk_score" in crit
    assert "overall_score" in crit
    assert "band" in crit

    res_crit_get = client.get("/api/v1/criticality", headers=auth_headers)
    assert res_crit_get.status_code == 200

    # 6. Alerts
    eval_alerts = client.post("/api/v1/alerts/evaluate", headers=auth_headers)
    assert eval_alerts.status_code == 200
    res_alerts = client.get("/api/v1/alerts", headers=auth_headers)
    assert res_alerts.status_code == 200
    alerts = res_alerts.json()
    assert len(alerts) > 0
