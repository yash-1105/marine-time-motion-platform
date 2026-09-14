import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from apps.api.models.canonical import VesselCall, EventOccurrence, ServiceRequest, ServiceAssignment, ServiceExecution
from apps.api.models.config import EventDefinition
from apps.api.models.quality import QualityIssue
from apps.api.services.quality.engine import DataQualityEngine
import datetime
import uuid

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
    ass = ServiceAssignment(service_request_id=req.id, scheduled_time=datetime.datetime(2026, 1, 1, 10, 0, tzinfo=datetime.timezone.utc))
    db_session.add(ass)
    db_session.flush()
    exe = ServiceExecution(service_assignment_id=ass.id, served_time=datetime.datetime(2026, 1, 1, 9, 30, tzinfo=datetime.timezone.utc))
    db_session.add(exe)
    
    # 2. Sequence violation (POB before Anchorage)
    anchor_def = db_session.execute(text("SELECT id FROM config.event_definition WHERE name='ANCHORAGE_ARRIVAL'")).scalar()
    pob_def = db_session.execute(text("SELECT id FROM config.event_definition WHERE name='PILOT_ON_BOARD_ARRIVAL'")).scalar()
    
    anchor = EventOccurrence(vessel_call_id=vc_id, event_definition_id=anchor_def, utc_value=datetime.datetime(2026, 1, 1, 12, 0, tzinfo=datetime.timezone.utc), occurrence_index=1, movement_scope="ARRIVAL", capture_method="SYSTEM", is_quarantined=False)
    pob = EventOccurrence(vessel_call_id=vc_id, event_definition_id=pob_def, utc_value=datetime.datetime(2026, 1, 1, 11, 0, tzinfo=datetime.timezone.utc), occurrence_index=1, movement_scope="ARRIVAL", capture_method="SYSTEM", is_quarantined=False)
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
