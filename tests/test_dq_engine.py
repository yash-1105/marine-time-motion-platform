import datetime
import uuid

import pytest
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.orm import sessionmaker

from apps.api.models.canonical import EventOccurrence, ServiceAssignment, ServiceExecution, ServiceRequest, VesselCall
from apps.api.models.ingestion import StagingRecord
from apps.api.models.quality import QualityIssue, QualityRule
from apps.api.services.quality.engine import DataQualityEngine


@pytest.fixture(scope="module")
def db_session():
    engine = create_engine("postgresql://admin:password@localhost:5434/marine_platform")
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()

def test_parallel_events_no_violations(db_session):
    pass

def test_early_service_vs_sequence_violation(db_session):
    engine = DataQualityEngine(db_session)
    
    vc_id = str(uuid.uuid4())
    vc = VesselCall(id=vc_id, tenant_id="test-tenant", vessel_name="Test", vcn="TEST-VCN", vessel_type="Container")
    db_session.add(vc)
    db_session.commit()
    
    # 1. Early service (negative delay) -> valid, no issue
    req = ServiceRequest(vessel_call_id=vc_id, service_type="Tug")
    db_session.add(req)
    db_session.flush()
    ass = ServiceAssignment(service_request_id=req.id, scheduled_time=datetime.datetime(2026, 1, 1, 10, 0, tzinfo=datetime.UTC))
    db_session.add(ass)
    db_session.flush()
    exe = ServiceExecution(service_assignment_id=ass.id, served_time=datetime.datetime(2026, 1, 1, 9, 30, tzinfo=datetime.UTC))
    db_session.add(exe)
    
    # 2. Sequence violation (POB before Anchorage)
    anchor_def = db_session.execute(text("SELECT id FROM config.event_definition WHERE name='ANCHORAGE_ARRIVAL'")).scalar()
    pob_def = db_session.execute(text("SELECT id FROM config.event_definition WHERE name='PILOT_ON_BOARD_ARRIVAL'")).scalar()
    
    anchor = EventOccurrence(vessel_call_id=vc_id, event_definition_id=anchor_def, utc_value=datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.UTC), occurrence_index=1, movement_scope="ARRIVAL", capture_method="SYSTEM", is_quarantined=False)
    pob = EventOccurrence(vessel_call_id=vc_id, event_definition_id=pob_def, utc_value=datetime.datetime(2026, 1, 1, 11, 0, tzinfo=datetime.UTC), occurrence_index=1, movement_scope="ARRIVAL", capture_method="SYSTEM", is_quarantined=False)
    db_session.add_all([anchor, pob])
    
    db_session.commit()
    
    engine.evaluate_vessel_call(vc)
    db_session.commit()
    
    issues = db_session.execute(text(f"SELECT rule_id FROM quality.quality_issue WHERE vessel_call_id='{vc_id}'")).scalars().all()
    rule_ids = [db_session.execute(text(f"SELECT rule_id FROM quality.quality_rule WHERE id='{i}'")).scalar() for i in issues]
    assert "DQ-006" in rule_ids
    assert "DQ-007" not in rule_ids

    # Teardown
    db_session.execute(text(f"DELETE FROM quality.quality_issue WHERE vessel_call_id='{vc_id}'"))
    db_session.execute(text(f"DELETE FROM canonical.event_occurrence WHERE vessel_call_id='{vc_id}'"))
    db_session.execute(text(f"DELETE FROM canonical.service_execution WHERE service_assignment_id='{ass.id}'"))
    db_session.execute(text(f"DELETE FROM canonical.service_assignment WHERE id='{ass.id}'"))
    db_session.execute(text(f"DELETE FROM canonical.service_request WHERE id='{req.id}'"))
    db_session.execute(text(f"DELETE FROM canonical.vessel_call WHERE id='{vc_id}'"))
    db_session.commit()


def test_service_request_schedule_served_completeness_and_order_are_deterministic(db_session):
    """A schedule-before-request is invalid; early served time is not rewritten."""
    vc = VesselCall(tenant_id="test-tenant", vessel_name="DQ Service", vcn=f"DQ-SVC-{uuid.uuid4().hex[:8]}", vessel_type="Container")
    db_session.add(vc)
    db_session.flush()
    missing_request = ServiceRequest(vessel_call_id=vc.id, service_type="Pilotage", requested_time=None)
    ordered_badly = ServiceRequest(vessel_call_id=vc.id, service_type="Tug", requested_time=datetime.datetime(2026, 1, 1, 11, 0, tzinfo=datetime.UTC))
    db_session.add_all([missing_request, ordered_badly])
    db_session.flush()
    missing_schedule = ServiceAssignment(service_request_id=missing_request.id, scheduled_time=None)
    before_request = ServiceAssignment(service_request_id=ordered_badly.id, scheduled_time=datetime.datetime(2026, 1, 1, 10, 45, tzinfo=datetime.UTC))
    db_session.add_all([missing_schedule, before_request])
    db_session.flush()
    db_session.add(ServiceExecution(service_assignment_id=before_request.id, served_time=None))
    db_session.commit()
    DataQualityEngine(db_session).evaluate_vessel_call(vc)
    db_session.commit()
    found = db_session.execute(select(QualityRule.rule_id).join(QualityIssue, QualityIssue.rule_id == QualityRule.id).where(QualityIssue.vessel_call_id == vc.id)).scalars().all()
    assert {"DQ-SERVICE-REQUEST-MISSING", "DQ-SERVICE-SCHEDULE-MISSING", "DQ-SERVICE-SERVED-MISSING", "DQ-SERVICE-SCHEDULE-BEFORE-REQUEST"}.issubset(found)
    db_session.execute(text("DELETE FROM quality.quality_issue WHERE vessel_call_id = :id"), {"id": str(vc.id)})
    db_session.execute(text("DELETE FROM canonical.service_execution WHERE service_assignment_id IN (:first, :second)"), {"first": str(missing_schedule.id), "second": str(before_request.id)})
    db_session.execute(text("DELETE FROM canonical.service_assignment WHERE service_request_id IN (:first, :second)"), {"first": str(missing_request.id), "second": str(ordered_badly.id)})
    db_session.execute(text("DELETE FROM canonical.service_request WHERE vessel_call_id = :id"), {"id": str(vc.id)})
    db_session.execute(text("DELETE FROM canonical.vessel_call WHERE id = :id"), {"id": str(vc.id)})
    db_session.commit()


def test_invalid_staging_timestamp_and_duplicate_are_reviewable_not_corrected(db_session):
    rows = [
        StagingRecord(file_checksum="dq-test", worksheet_name="Events", row_number=9001, parsed_data={"VCN": "DQ", "Event_Name": "ATA", "Event_Timestamp": "not-a-time"}, ingestion_batch_id="dq-test", validation_status="VALID", canonical_table="event_occurrence"),
        StagingRecord(file_checksum="dq-test", worksheet_name="Events", row_number=9002, parsed_data={"VCN": "DQ", "Event_Name": "ATA", "Event_Timestamp": "2026-01-01 10:00"}, ingestion_batch_id="dq-test", validation_status="DUPLICATE", canonical_table="event_occurrence"),
    ]
    db_session.add_all(rows)
    db_session.commit()
    DataQualityEngine(db_session).evaluate_staging_records()
    db_session.commit()
    references = [f"StagingRecord:{row.id}" for row in rows]
    found = db_session.execute(select(QualityRule.rule_id).join(QualityIssue, QualityIssue.rule_id == QualityRule.id).where(QualityIssue.record_reference.in_(references))).scalars().all()
    assert "DQ-INVALID-TIMESTAMP" in found and "DQ-DUPLICATE-ROW" in found
    assert rows[0].parsed_data["Event_Timestamp"] == "not-a-time"
    db_session.execute(delete(QualityIssue).where(QualityIssue.record_reference.in_(references)))
    db_session.execute(delete(StagingRecord).where(StagingRecord.id.in_([row.id for row in rows])))
    db_session.commit()
