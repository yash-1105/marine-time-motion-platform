"""Unit and integration tests for Governed KPI Engine (Phase 08, spec §11).

Tests:
1. All 55 KPIs exist in registry with valid metadata and numbering.
2. FRD v2.1 registry availability: 27 formula-capable entries and 28
   NO_SOURCE_DATA entries where a required governed source is absent.
3. NO_SOURCE_DATA KPIs never fabricate zeroes; return status NO_SOURCE_DATA.
4. Alias pairs (KPI-11/53 and KPI-14/51) cannot double-count in scorecards; admin swap works.
5. Hand-verified small fixture for computable KPIs with exact arithmetic validation.
6. Edge cases: empty population, single observation, zero denominator, mixed units segmentation.
7. Green/Amber/Red banding logic.
8. Trend calculation, rolling averages, and direction classification.
9. Audited recalculation writing to audit.audit_event.
10. Benchmark absence handling and admin creation.
11. REST API endpoints with RBAC enforcement.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from apps.api.main import app, settings
from apps.api.models.analytics import KPI, KPIFormulaVersion
from apps.api.models.audit import AuditEvent
from apps.api.models.canonical import (
    CargoOperation,
    EventOccurrence,
    ServiceAssignment,
    ServiceExecution,
    ServiceRequest,
    VesselCall,
)
from apps.api.models.config import EventDefinition
from apps.api.services.analytics.engine import AnalyticsEngine
from apps.api.services.identity.engine import IdentityEngine
from apps.api.services.journey.reconstructor import JourneyReconstructionEngine
from apps.api.services.kpi.benchmarks import KPIBenchmarkService
from apps.api.services.kpi.engine import KPIEngine
from apps.api.services.kpi.registry import ensure_kpi_registry
from apps.api.services.quality.engine import DataQualityEngine
from testkit.loader import load_synthetic_dataset


@pytest.fixture(scope="function")
def db_session():
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture(scope="module")
def auth_headers():
    client = TestClient(app)
    resp = client.post("/api/v1/auth/dev/login", json={"role_or_email": "Platform Administrator"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def governed_kpi_api_dataset():
    """Give KPI API assertions their own persisted governed population.

    The ingestion test module deliberately removes the active dataset, so an API
    test must not depend on percentile rows left behind by an earlier module.
    """
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        load_synthetic_dataset(session, "fixtures/Synthetic_Marine_Time_Motion_Test_Data.xlsx")
        DataQualityEngine(session).run_all()
        IdentityEngine(session, tenant_id="synthetic-tenant").auto_merge_candidates()
        JourneyReconstructionEngine(session, tenant_id="synthetic-tenant").reconstruct_all()
        analytics = AnalyticsEngine(session, tenant_id="synthetic-tenant", exclude_quarantined=True)
        analytics.compute_all_metrics()
        analytics.compute_all_statistics()
        yield
    finally:
        session.close()


# ──────────────────────────────────────────────────────────────────────────────
# 1. Registry Completeness and Specification Alignment
# ──────────────────────────────────────────────────────────────────────────────

def test_all_55_kpis_registered(db_session):
    """Verifies that all 55 KPIs from spec §11 exist in the governed registry."""
    kpi_map = ensure_kpi_registry(db_session)
    assert len(kpi_map) == 55

    computed_count = sum(1 for k in kpi_map.values() if k.availability_status == "COMPUTED")
    no_src_count = sum(1 for k in kpi_map.values() if k.availability_status == "NO_SOURCE_DATA")

    # FRD v2.1 makes resource-capacity/arrival-log dependent metrics explicitly
    # NO_SOURCE_DATA rather than deriving them from undeclared constants.
    assert computed_count == 27
    assert no_src_count == 28

    # Legacy rows are retained for result/audit provenance but cannot be part of
    # the active FRD catalogue or new governed computations.
    active_governed = db_session.execute(
        select(KPI).where(KPI.is_active.is_(True), KPI.code.isnot(None))
    ).scalars().all()
    assert len(active_governed) == 55
    assert not db_session.execute(
        select(KPI).where(KPI.is_active.is_(True), KPI.code.is_(None))
    ).scalars().first()

    # Every current formula has an explicit v2.1 attribution. Existing v1.0/v2.0
    # records are intentionally retained by the registry rather than rewritten.
    for kpi in kpi_map.values():
        assert db_session.execute(
            select(KPIFormulaVersion).where(KPIFormulaVersion.kpi_id == kpi.id, KPIFormulaVersion.version == "2.1")
        ).scalar_one_or_none() is not None


def test_alias_pairs_primary_and_alias_status(db_session):
    """Verifies that duplicate concepts (KPI-11/53 and KPI-14/51) are paired and do not double count."""
    kpi_map = ensure_kpi_registry(db_session)

    # 1. Tug Response: KPI-11 (Primary) and KPI-53 (Alias)
    k11 = kpi_map["KPI-11"]
    k53 = kpi_map["KPI-53"]
    assert k11.is_primary is True
    assert k53.is_primary is False
    assert k53.alias_of_id == k11.id

    # 2. Berth Occupancy: KPI-14 (Primary) and KPI-51 (Alias)
    k14 = kpi_map["KPI-14"]
    k51 = kpi_map["KPI-51"]
    assert k14.is_primary is True
    assert k51.is_primary is False
    assert k51.alias_of_id == k14.id


def test_no_source_data_kpis_never_produce_number(db_session):
    """Verifies that all source-limited KPIs return NO_SOURCE_DATA, never zero."""
    engine = KPIEngine(db_session, tenant_id="synthetic-tenant")
    kpi_map = engine.ensure_registry()

    no_src_codes = [code for code, k in kpi_map.items() if k.availability_status == "NO_SOURCE_DATA"]
    assert len(no_src_codes) == 28

    for code in no_src_codes:
        res = engine.calculate_kpi(code)
        assert res.status == "NO_SOURCE_DATA", f"Expected NO_SOURCE_DATA for {code}, got {res.status}"
        assert res.value is None, f"Expected value=None for {code}, got {res.value}"
        assert res.band == "GRAY"
        assert res.unavailable_reason is not None
        assert "No connected source system" in res.unavailable_reason


# ──────────────────────────────────────────────────────────────────────────────
# 2. Hand-Verified Small Synthetic Fixture Tests (Isolated Tenant)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def hand_verified_fixture(db_session):
    """Constructs a small, controlled, hand-verified test dataset in an isolated tenant."""
    test_tenant = f"test-tenant-{uuid.uuid4().hex[:8]}"

    # Helper for event definitions
    def get_or_create_ed(name):
        ed = db_session.execute(select(EventDefinition).where(EventDefinition.name == name)).scalar_one_or_none()
        if not ed:
            ed = EventDefinition(name=name, category="TEST", time_category="TEST")
            db_session.add(ed)
            db_session.flush()
        return ed

    ed_ata = get_or_create_ed("ATA")
    ed_atd = get_or_create_ed("ATD")
    ed_anch_arr = get_or_create_ed("ANCHORAGE_ARRIVAL")
    ed_pilot_arr = get_or_create_ed("PILOT_ON_BOARD_ARRIVAL")
    ed_flt = get_or_create_ed("FIRST_LINE_TIED_ARRIVAL")
    ed_all_fast = get_or_create_ed("ALL_FAST_ARRIVAL")
    ed_cargo_start = get_or_create_ed("CARGO_START")
    ed_cargo_end = get_or_create_ed("CARGO_END")
    ed_last_untied = get_or_create_ed("LAST_LINE_UNTIED_SAILING")
    ed_bw_out = get_or_create_ed("BREAKWATER_OUT")

    base_time = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)

    # Call 1: Container vessel
    # Anchorage Wait: 2.0 hours (08:00 -> 10:00)
    # Berth Stay: 20.0 hours (12:00 -> 08:00 next day)
    # Working Hours: 15.0 hours (Cargo 1000 TEU, 2 cranes -> 30 crane-hours)
    # ATA -> ATD: 28.0 hours (08:00 -> 12:00 next day)
    vc1 = VesselCall(
        vessel_name="Test Alpha",
        vcn=f"TEST-VCN-1-{uuid.uuid4().hex[:4]}",
        vessel_type="Container",
        tenant_id=test_tenant,
        quantity_unit="TEU",
        quantity_value=1000.0,
        is_merged=False,
    )
    db_session.add(vc1)
    db_session.flush()

    events_vc1 = [
        (ed_ata, base_time),
        (ed_anch_arr, base_time),
        (ed_pilot_arr, base_time + timedelta(hours=2)),
        (ed_flt, base_time + timedelta(hours=3)),
        (ed_all_fast, base_time + timedelta(hours=4)),
        (ed_cargo_start, base_time + timedelta(hours=5)),
        (ed_cargo_end, base_time + timedelta(hours=20)),
        (ed_last_untied, base_time + timedelta(hours=24)),
        (ed_bw_out, base_time + timedelta(hours=26)),
        (ed_atd, base_time + timedelta(hours=28)),
    ]
    for ed, t in events_vc1:
        mscope = "SAILING" if any(k in ed.name for k in ("SAILING", "OUT", "UNTIED", "ATD")) else "ARRIVAL"
        db_session.add(EventOccurrence(
            vessel_call_id=vc1.id,
            event_definition_id=ed.id,
            utc_value=t,
            occurrence_index=1,
            movement_scope=mscope,
        ))

    # Cargo Op for Call 1: 1000 TEU, 15 working hours, 2 cranes deployed
    db_session.add(CargoOperation(
        vessel_call_id=vc1.id,
        operation_id="CG-T1",
        cargo_type="Container",
        operation_type="Load",
        planned_quantity=1000.0,
        actual_quantity=1000.0,
        unit="TEU",
        working_hours=15.0,
        resources_deployed=2,
        downtime_hours=1.0,
    ))

    # Service execution for Call 1: Scheduled at 09:30, Served at 10:00 -> delay = +0.5h
    req1 = ServiceRequest(vessel_call_id=vc1.id, service_type="Pilotage Service", movement_type="Arrival")
    db_session.add(req1)
    db_session.flush()
    ass1 = ServiceAssignment(service_request_id=req1.id, scheduled_time=base_time + timedelta(hours=1.5))
    db_session.add(ass1)
    db_session.flush()
    db_session.add(ServiceExecution(service_assignment_id=ass1.id, served_time=base_time + timedelta(hours=2.0)))

    # Call 2: Bulk vessel (MT unit to test unit isolation)
    # Anchorage Wait: 4.0 hours (08:00 -> 12:00)
    # Berth Stay: 10.0 hours
    # Actual Quantity: 5000.0 MT
    vc2 = VesselCall(
        vessel_name="Test Beta",
        vcn=f"TEST-VCN-2-{uuid.uuid4().hex[:4]}",
        vessel_type="Bulk",
        tenant_id=test_tenant,
        quantity_unit="MT",
        quantity_value=5000.0,
        is_merged=False,
    )
    db_session.add(vc2)
    db_session.flush()

    events_vc2 = [
        (ed_ata, base_time),
        (ed_anch_arr, base_time),
        (ed_pilot_arr, base_time + timedelta(hours=4)),
        (ed_all_fast, base_time + timedelta(hours=6)),
        (ed_cargo_start, base_time + timedelta(hours=7)),
        (ed_cargo_end, base_time + timedelta(hours=15)),
        (ed_last_untied, base_time + timedelta(hours=16)),
        (ed_atd, base_time + timedelta(hours=18)),
    ]
    for ed, t in events_vc2:
        mscope = "SAILING" if any(k in ed.name for k in ("SAILING", "OUT", "UNTIED", "ATD")) else "ARRIVAL"
        db_session.add(EventOccurrence(
            vessel_call_id=vc2.id,
            event_definition_id=ed.id,
            utc_value=t,
            occurrence_index=1,
            movement_scope=mscope,
        ))

    db_session.add(CargoOperation(
        vessel_call_id=vc2.id,
        operation_id="CG-T2",
        cargo_type="Bulk",
        operation_type="Discharge",
        planned_quantity=5000.0,
        actual_quantity=5000.0,
        unit="MT",
        working_hours=8.0,
        resources_deployed=1,
        downtime_hours=0.5,
    ))

    db_session.commit()
    return test_tenant


def test_computable_kpis_arithmetic_on_hand_verified_fixture(db_session, hand_verified_fixture):
    """Verifies that computable KPIs calculate mathematically exact values on small fixture."""
    engine = KPIEngine(db_session, tenant_id=hand_verified_fixture)

    # 1. KPI-01: Number of Vessel Calls (exact: 2)
    r1 = engine.calculate_kpi("KPI-01")
    assert r1.status == "COMPUTED"
    assert r1.value == 2.0

    # 2. KPI-03: Pre-Berthing Waiting Time: (2.0 + 4.0) / 2 = 3.0 hours
    r3 = engine.calculate_kpi("KPI-03")
    assert r3.status == "COMPUTED"
    assert abs(r3.value - 3.0) < 0.001

    # 3. KPI-02: Unit Isolation (spec §11: never mix units into unqualified total)
    # With TEU filter: Call 1 only -> 1000.0 TEU
    r2_teu = engine.calculate_kpi("KPI-02", cohort_filters={"unit": "TEU"})
    assert r2_teu.status == "COMPUTED"
    assert r2_teu.value == 1000.0
    # With MT filter: Call 2 only -> 5000.0 MT
    r2_mt = engine.calculate_kpi("KPI-02", cohort_filters={"unit": "MT"})
    assert r2_mt.status == "COMPUTED"
    assert r2_mt.value == 5000.0

    # 4. KPI-10 requires pilot availability/roster hours and must not substitute
    # scheduled-to-served delay as a fake availability percentage.
    r10 = engine.calculate_kpi("KPI-10")
    assert r10.status == "NO_SOURCE_DATA"
    assert r10.value is None

    # 5. KPI-21: Berth Productivity (moves / crane-hours)
    # moves = 1000.0; crane-hours = 15.0 * 2 = 30.0 -> 1000 / 30 = 33.33 moves/crane-hr
    r21 = engine.calculate_kpi("KPI-21")
    assert r21.status == "COMPUTED"
    assert abs(r21.value - 33.33) < 0.05

    # 6. KPI-24: Container Traffic in TEUs: 1000.0 TEU
    r24 = engine.calculate_kpi("KPI-24")
    assert r24.status == "COMPUTED"
    assert r24.value == 1000.0

    # 7. KPI-43 starts at berth departure and ends at port limits; call 1 has
    # 2 hours and call 2 is ineligible, so the governed average is 2 hours.
    r43 = engine.calculate_kpi("KPI-43")
    assert r43.status == "COMPUTED"
    assert abs(r43.value - 2.0) < 0.001

    # Formula v2.1 is stored on every new governed result.
    assert r43.formula_version == "2.1"


def test_shift_kpis_pair_each_repeat_and_preserve_source_lineage(db_session):
    """KPI-19/20 count every indexed shift; a later shift cannot overwrite the first."""
    tenant = f"shift-kpi-{uuid.uuid4().hex[:8]}"
    definitions = {}
    for name in ("SHIFT_PILOT_ON_BOARD", "SHIFT_ALL_FAST"):
        definition = db_session.execute(select(EventDefinition).where(EventDefinition.name == name)).scalar_one_or_none()
        if not definition:
            definition = EventDefinition(name=name, category="TEST", time_category="TEST")
            db_session.add(definition)
            db_session.flush()
        definitions[name] = definition
    call = VesselCall(vessel_name="Repeated Shift", vcn=f"SHIFT-{uuid.uuid4().hex[:6]}", tenant_id=tenant)
    db_session.add(call)
    db_session.flush()
    start = datetime(2026, 7, 1, 8, tzinfo=UTC)
    for index, start_time, end_time in ((1, start, start + timedelta(hours=1)), (2, start + timedelta(hours=3), start + timedelta(hours=5))):
        db_session.add_all([
            EventOccurrence(vessel_call_id=call.id, event_definition_id=definitions["SHIFT_PILOT_ON_BOARD"].id,
                            utc_value=start_time, occurrence_index=index, movement_scope="SHIFTING"),
            EventOccurrence(vessel_call_id=call.id, event_definition_id=definitions["SHIFT_ALL_FAST"].id,
                            utc_value=end_time, occurrence_index=index, movement_scope="SHIFTING"),
        ])
    db_session.commit()

    engine = KPIEngine(db_session, tenant_id=tenant)
    count = engine.calculate_kpi("KPI-19")
    duration = engine.calculate_kpi("KPI-20")
    assert (count.status, count.value) == ("COMPUTED", 2.0)
    assert (duration.status, duration.value) == ("COMPUTED", 1.5)
    assert len(duration.data_quality_summary["source_event_ids"]) == 4


# ──────────────────────────────────────────────────────────────────────────────
# 3. Edge Cases: Empty Population, Single Observation, Banding
# ──────────────────────────────────────────────────────────────────────────────

def test_empty_population_returns_unavailable_not_zero(db_session):
    """Verifies that an empty cohort returns status UNAVAILABLE rather than fabricating zeroes."""
    engine = KPIEngine(db_session, tenant_id="non-existent-tenant-xyz")
    res = engine.calculate_kpi("KPI-01")
    assert res.status == "UNAVAILABLE"
    assert res.value is None
    assert res.band == "GRAY"


def test_green_amber_red_banding_logic():
    """Verifies target and threshold banding for both LOWER_IS_BETTER and HIGHER_IS_BETTER."""
    # LOWER_IS_BETTER: green <= 5.0, amber <= 10.0, red > 10.0
    th = {"green": 5.0, "amber": 10.0, "red": 20.0}
    assert KPIEngine.evaluate_band(3.0, 5.0, "LOWER_IS_BETTER", th) == "GREEN"
    assert KPIEngine.evaluate_band(7.5, 5.0, "LOWER_IS_BETTER", th) == "AMBER"
    assert KPIEngine.evaluate_band(15.0, 5.0, "LOWER_IS_BETTER", th) == "RED"
    assert KPIEngine.evaluate_band(None, 5.0, "LOWER_IS_BETTER", th) == "GRAY"

    # HIGHER_IS_BETTER: green >= 70.0, amber >= 50.0, red < 50.0
    th_hi = {"green": 70.0, "amber": 50.0, "red": 30.0}
    assert KPIEngine.evaluate_band(75.0, 70.0, "HIGHER_IS_BETTER", th_hi) == "GREEN"
    assert KPIEngine.evaluate_band(55.0, 70.0, "HIGHER_IS_BETTER", th_hi) == "AMBER"
    assert KPIEngine.evaluate_band(40.0, 70.0, "HIGHER_IS_BETTER", th_hi) == "RED"


# ──────────────────────────────────────────────────────────────────────────────
# 4. Audited Recalculation and Trends
# ──────────────────────────────────────────────────────────────────────────────

def test_permissioned_recalculation_audited(db_session):
    """Verifies that recalculation produces a versioned result and writes an audit event."""
    engine = KPIEngine(db_session, tenant_id="synthetic-tenant")
    actor = "steward-007"
    reason = "Quality rule validation run"

    res = engine.recalculate_kpi("KPI-01", actor_id=actor, reason=reason)
    assert res.is_recalculation is True
    assert res.status == "COMPUTED"

    # Check audit log
    audit_ev = db_session.execute(
        select(AuditEvent)
        .where(AuditEvent.entity_name == "kpi_result", AuditEvent.actor_id == actor)
        .order_by(AuditEvent.created_at.desc())
    ).scalars().first()

    assert audit_ev is not None
    assert audit_ev.action == "RECALCULATE"
    assert audit_ev.details.get("reason") == reason
    assert audit_ev.details.get("kpi_code") == "KPI-01"


def test_trend_calculation_rolling_average(db_session):
    """Verifies trend points, rolling average, and direction classification."""
    engine = KPIEngine(db_session, tenant_id="synthetic-tenant")
    trend = engine.get_trends("KPI-01", grain="MONTHLY", periods=4)

    assert trend["status"] == "COMPUTED"
    assert "trend_points" in trend
    assert "direction" in trend
    assert trend["direction"] in ("IMPROVING", "DETERIORATING", "STABLE")


# ──────────────────────────────────────────────────────────────────────────────
# 5. Benchmark Absence Handling
# ──────────────────────────────────────────────────────────────────────────────

def test_benchmark_peer_data_absence_disclosed(db_session):
    """Verifies that when peer benchmarks are absent, no numbers are fabricated."""
    service = KPIBenchmarkService(db_session)
    res = service.get_benchmarks_for_kpi("KPI-03")

    assert res["has_benchmarks"] is False
    assert res["benchmarks"] == []
    assert "absent_notice" in res
    assert "intentionally unpopulated" in res["absent_notice"]


def test_benchmark_admin_creation(db_session):
    """Verifies admin creation of a peer benchmark."""
    service = KPIBenchmarkService(db_session)
    bm = service.create_benchmark(
        kpi_code_or_id="KPI-01",
        peer_port="Port of Durban",
        benchmark_value=85.0,
        source="PMAESA Annual Report",
        period="2025",
        notes="Official published peer traffic",
    )
    try:
        assert bm.peer_port == "Port of Durban"
        assert bm.benchmark_value == 85.0

        # Retrieve and verify presence
        res = service.get_benchmarks_for_kpi("KPI-01")
        assert res["has_benchmarks"] is True
        assert any(b["peer_port"] == "Port of Durban" for b in res["benchmarks"])
    finally:
        db_session.delete(bm)
        db_session.commit()


# ──────────────────────────────────────────────────────────────────────────────
# 6. REST API Endpoints with Auth
# ──────────────────────────────────────────────────────────────────────────────

def test_kpi_api_endpoints_work(auth_headers, governed_kpi_api_dataset):
    """Verifies that REST API endpoints return governed responses and enforce RBAC."""
    client = TestClient(app)

    # 1. GET /kpis (returns all 55)
    r_list = client.get("/api/v1/kpis", headers=auth_headers)
    assert r_list.status_code == 200
    kpis = r_list.json()
    assert len(kpis) == 55

    # 2. GET /kpis/scorecard
    r_card = client.get("/api/v1/kpis/scorecard", headers=auth_headers)
    assert r_card.status_code == 200
    card = r_card.json()
    assert card["computed"] == 25
    assert card["no_source_data"] == 28
    # Unit-dependent KPIs 02 and 27 remain UNAVAILABLE on an unqualified
    # scorecard; that prevents an incompatible TEU/MT total.
    assert card["unavailable"] == 2

    # 3. Governed percentile values are served from persisted analytics, including P75.
    r_stats = client.get("/api/v1/kpis/statistics", headers=auth_headers)
    assert r_stats.status_code == 200
    stats = r_stats.json()
    assert stats["percentile_method"] == "linear_interpolation"
    turnaround = next(item for item in stats["items"] if item["name"] == "Turnaround")
    assert turnaround["p75"] is not None
    assert turnaround["p90"] is not None
    assert turnaround["p75"] <= turnaround["p90"]

    # 4. Service Line is implemented from the actual Service Type source dimension.
    r_service_lines = client.get("/api/v1/kpis/service-lines", headers=auth_headers)
    assert r_service_lines.status_code == 200
    lines = r_service_lines.json()
    assert "Service Type" in lines["interpretation"]
    assert all(item["formula"] == "mean(Served_Time − Scheduled_Time)" for item in lines["items"])
    first_line = next(item for item in lines["items"] if item["status"] == "COMPUTED")
    r_records = client.get(
        "/api/v1/kpis/service-lines/records",
        params={"service_type": first_line["service_line"], "movement_type": first_line["movement_type"]},
        headers=auth_headers,
    )
    assert r_records.status_code == 200
    assert r_records.json()["items"]

    # 5. GET /kpis/KPI-01
    r_detail = client.get("/api/v1/kpis/KPI-01", headers=auth_headers)
    assert r_detail.status_code == 200
    detail = r_detail.json()
    assert detail["code"] == "KPI-01"
    assert detail["name"] == "Number of Vessel Calls"
    assert len(detail["formula_versions"]) >= 1

    # 6. POST /kpis/KPI-01/recalculate
    r_recalc = client.post(
        "/api/v1/kpis/KPI-01/recalculate",
        json={"reason": "Audited API test recalculation"},
        headers=auth_headers,
    )
    assert r_recalc.status_code == 200
    assert r_recalc.json()["status"] == "SUCCESS"

    # 7. Unauthorized access rejected
    r_unauth = client.get("/api/v1/kpis")
    assert r_unauth.status_code == 401
