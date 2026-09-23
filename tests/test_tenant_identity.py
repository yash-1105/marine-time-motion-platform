"""Regression coverage for authenticated tenant propagation and isolation."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from apps.api.auth.principal import UserPrincipal
from apps.api.auth.scope import DataScope
from apps.api.auth.tenant import resolve_principal_tenant
from apps.api.core.database import SessionLocal
from apps.api.main import app
from apps.api.models.analytics import KPI, KPIResult, LeadTimeDefinition, StatisticalAggregate
from apps.api.models.auth import SessionRecord
from apps.api.models.canonical import ServiceAssignment, ServiceExecution, ServiceRequest, VesselCall
from apps.api.services.auth_service import create_user_session


def _principal(tenant_id: str) -> UserPrincipal:
    return UserPrincipal(
        user_id=f"user-{tenant_id}",
        email=f"{tenant_id}@example.test",
        roles=[],
        permissions=["view"],
        data_scope=DataScope(tenant_id=tenant_id, port_id="*", terminal_id="*"),
        is_synthetic=False,
    )


def _token(db, tenant_id: str) -> tuple[dict[str, str], str]:
    session = create_user_session(
        db=db,
        user_id=f"user-{tenant_id}",
        email=f"{tenant_id}@example.test",
        roles=[],
        permissions=["view"],
        data_scope={"tenant_id": tenant_id, "port_id": "*", "terminal_id": "*"},
    )
    return {"Authorization": f"Bearer {session['access_token']}"}, session["session_id"]


def _add_service(db, vessel_call_id, movement: str, minutes_from_schedule: int):
    requested = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
    request = ServiceRequest(
        vessel_call_id=vessel_call_id,
        service_type="Pilotage Service",
        movement_type=movement,
        submission_time=requested - timedelta(minutes=30),
        requested_time=requested,
    )
    db.add(request)
    db.flush()
    assignment = ServiceAssignment(
        service_request_id=request.id,
        scheduled_time=requested + timedelta(minutes=15),
    )
    db.add(assignment)
    db.flush()
    execution = ServiceExecution(
        service_assignment_id=assignment.id,
        served_time=assignment.scheduled_time + timedelta(minutes=minutes_from_schedule),
    )
    db.add(execution)
    db.flush()
    return request, assignment, execution


def test_tenant_aliases_are_not_equivalent_and_client_override_is_rejected():
    principal = _principal("tenant-a")
    assert resolve_principal_tenant(principal) == "tenant-a"
    assert principal.data_scope.allows_tenant("tenant-a")
    assert not principal.data_scope.allows_tenant("tenant-b")

    try:
        resolve_principal_tenant(principal, "tenant-b")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403
    else:
        raise AssertionError("A client tenant override must be rejected")


def test_tenant_a_and_b_are_isolated_across_service_journey_kpi_and_statistics_apis():
    db = SessionLocal()
    client = TestClient(app)
    suffix = uuid4().hex[:10]
    tenant_a = f"tenant-a-{suffix}"
    tenant_b = f"tenant-b-{suffix}"
    vcn = f"OVERLAP-{suffix}"
    calls = []
    services = []
    aggregates = []
    kpi_results = []
    session_ids = []
    try:
        call_a = VesselCall(vessel_name="Shared Vessel", vcn=vcn, tenant_id=tenant_a)
        call_b = VesselCall(vessel_name="Shared Vessel", vcn=vcn, tenant_id=tenant_b)
        db.add_all([call_a, call_b])
        db.flush()
        calls.extend([call_a, call_b])

        for movement, offset in (("Arrival", 20), ("Sailing", -10), ("Shifting", -5)):
            services.append(_add_service(db, call_a.id, movement, offset))
            services.append(_add_service(db, call_b.id, movement, offset + 7))

        definition = db.execute(select(LeadTimeDefinition).limit(1)).scalar_one()
        aggregates.extend(
            [
                StatisticalAggregate(
                    tenant_id=tenant_a,
                    definition_id=definition.id,
                    cohort_key=f"tenant-isolation-{suffix}",
                    observation_count=1,
                    mean_hours=1.0,
                    percentile_method="linear_interpolation",
                ),
                StatisticalAggregate(
                    tenant_id=tenant_b,
                    definition_id=definition.id,
                    cohort_key=f"tenant-isolation-{suffix}",
                    observation_count=1,
                    mean_hours=2.0,
                    percentile_method="linear_interpolation",
                ),
            ]
        )
        db.add_all(aggregates)

        kpi = db.execute(select(KPI).where(KPI.is_active.is_(True)).limit(1)).scalar_one()
        kpi_results.extend(
            [
                KPIResult(tenant_id=tenant_a, kpi_id=kpi.id, value=11, status="COMPUTED", calculated_at=datetime.now(UTC)),
                KPIResult(tenant_id=tenant_b, kpi_id=kpi.id, value=22, status="COMPUTED", calculated_at=datetime.now(UTC)),
            ]
        )
        db.add_all(kpi_results)
        db.commit()

        headers_a, session_a = _token(db, tenant_a)
        headers_b, session_b = _token(db, tenant_b)
        session_ids.extend([session_a, session_b])

        for headers, own_call, other_call, expected_value in (
            (headers_a, call_a, call_b, 11),
            (headers_b, call_b, call_a, 22),
        ):
            all_timings = client.get("/api/v1/delays/service-timings", headers=headers)
            assert all_timings.status_code == 200
            assert all_timings.json()["total"] == 3
            assert {row["vessel_call_id"] for row in all_timings.json()["items"]} == {str(own_call.id)}
            own_services = services[::2] if own_call is call_a else services[1::2]
            assert {row["service_request_id"] for row in all_timings.json()["items"]} == {
                str(request.id) for request, _assignment, _execution in own_services
            }
            assert {row["service_assignment_id"] for row in all_timings.json()["items"]} == {
                str(assignment.id) for _request, assignment, _execution in own_services
            }
            assert {row["service_execution_id"] for row in all_timings.json()["items"]} == {
                str(execution.id) for _request, _assignment, execution in own_services
            }

            arrival = client.get("/api/v1/delays/service-timings?leg=ARRIVAL_INWARD", headers=headers).json()
            sailing = client.get("/api/v1/delays/service-timings?leg=SAILING_OUTWARD", headers=headers).json()
            shifting = client.get("/api/v1/delays/service-timings?leg=SHIFTING", headers=headers).json()
            assert arrival["total"] == sailing["total"] == shifting["total"] == 1
            assert arrival["items"][0]["scheduling_gap_hours"] == 0.25
            assert sailing["items"][0]["execution_delay_hours"] < 0
            assert sailing["items"][0]["execution_delay_status"] == "EARLY"
            assert shifting["items"][0]["leg"] == "SHIFTING"

            journey_own = client.get(f"/api/v1/journey/{own_call.id}/service-timings", headers=headers)
            journey_other = client.get(f"/api/v1/journey/{other_call.id}/service-timings", headers=headers)
            assert len(journey_own.json()) == 3
            assert journey_other.status_code == 404
            assert client.get(f"/api/v1/journey/{other_call.id}/events", headers=headers).status_code == 404

            vessel_calls = client.get(f"/api/v1/operations/vessel-calls?search={vcn}", headers=headers)
            assert vessel_calls.status_code == 200
            assert len(vessel_calls.json()) == 1

            service_records = client.get(
                "/api/v1/kpis/service-lines/records?service_type=Pilotage%20Service",
                headers=headers,
            )
            assert service_records.status_code == 200
            assert {row["vessel_call_id"] for row in service_records.json()["items"]} == {str(own_call.id)}

            detail = client.get(f"/api/v1/kpis/{kpi.code}", headers=headers)
            assert detail.status_code == 200
            assert detail.json()["latest_result"]["value"] == expected_value

            stats = client.get(
                f"/api/v1/analytics/metrics/{definition.id}/stats?cohort_key=tenant-isolation-{suffix}",
                headers=headers,
            )
            assert stats.status_code == 200
            assert stats.json()["mean_hours"] == (1.0 if own_call is call_a else 2.0)

        override = client.get(
            f"/api/v1/operations/vessel-calls?tenant_id={tenant_b}",
            headers=headers_a,
        )
        assert override.status_code == 403
    finally:
        db.rollback()
        if session_ids:
            db.execute(delete(SessionRecord).where(SessionRecord.jti.in_(session_ids)))
        for result in kpi_results:
            db.delete(result)
        for aggregate in aggregates:
            db.delete(aggregate)
        for _request, _assignment, execution in services:
            db.delete(execution)
        db.flush()
        for _request, assignment, _execution in services:
            db.delete(assignment)
        db.flush()
        for request, _assignment, _execution in services:
            db.delete(request)
        db.flush()
        for call in calls:
            db.delete(call)
        db.commit()
        db.close()
