import os

models_dir = "apps/api/models"
os.makedirs(models_dir, exist_ok=True)

# canonical.py
with open(os.path.join(models_dir, "canonical.py"), "w") as f:
    f.write("""from sqlalchemy import Column, String, Integer, Float, Boolean, ForeignKey, DateTime, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from .base import BaseModel

class VesselCall(BaseModel):
    __tablename__ = 'vessel_call'
    __table_args__ = {'schema': 'canonical'}
    
    # Master attributes
    vessel_name = Column(String, nullable=False)
    imo_number = Column(String, nullable=True)
    vcn = Column(String, nullable=True, unique=True)
    vessel_type = Column(String, nullable=True)
    vessel_size_teu = Column(Integer, nullable=True)
    flag = Column(String, nullable=True)
    last_port_of_call = Column(String, nullable=True)
    next_port_of_call = Column(String, nullable=True)
    port_of_lading = Column(String, nullable=True)
    port_of_discharge = Column(String, nullable=True)
    reason_for_visit = Column(String, nullable=True)
    cargo_type = Column(String, nullable=True)
    commodity = Column(String, nullable=True)
    quantity_value = Column(Float, nullable=True)
    quantity_unit = Column(String, nullable=True)
    grt = Column(Float, nullable=True)
    loa_value = Column(Float, nullable=True)
    loa_unit = Column(String, nullable=True)
    dwt = Column(Float, nullable=True)
    forward_draft_value = Column(Float, nullable=True)
    forward_draft_unit = Column(String, nullable=True)
    aft_draft_value = Column(Float, nullable=True)
    aft_draft_unit = Column(String, nullable=True)
    call_sign = Column(String, nullable=True)

class EventOccurrence(BaseModel):
    __tablename__ = 'event_occurrence'
    __table_args__ = (
        UniqueConstraint('vessel_call_id', 'event_definition_id', 'occurrence_index', name='uq_event_occurrence'),
        {'schema': 'canonical'}
    )
    
    vessel_call_id = Column(ForeignKey('canonical.vessel_call.id'), nullable=False)
    event_definition_id = Column(ForeignKey('config.event_definition.id'), nullable=False)
    occurrence_index = Column(Integer, default=1, nullable=False)
    movement_scope = Column(String, nullable=False) # ARRIVAL|SHIFTING|SAILING
    
    # Timestamp envelope
    original_string = Column(String, nullable=True)
    parsed_value = Column(DateTime(timezone=True), nullable=True)
    source_timezone = Column(String, nullable=True)
    utc_value = Column(DateTime(timezone=True), nullable=False)
    capture_method = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    source_system = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    ingestion_batch_id = Column(String, nullable=True)
    correction_history = Column(JSON, nullable=True)
    
    inference_status = Column(String, nullable=True)
    human_review_state = Column(String, nullable=True)
    is_quarantined = Column(Boolean, default=False)

class ServiceRequest(BaseModel):
    __tablename__ = 'service_request'
    __table_args__ = {'schema': 'canonical'}
    vessel_call_id = Column(ForeignKey('canonical.vessel_call.id'), nullable=False)
    service_type = Column(String, nullable=False)
    requested_time = Column(DateTime(timezone=True), nullable=True)

class ServiceAssignment(BaseModel):
    __tablename__ = 'service_assignment'
    __table_args__ = {'schema': 'canonical'}
    service_request_id = Column(ForeignKey('canonical.service_request.id'), nullable=False)
    scheduled_time = Column(DateTime(timezone=True), nullable=True)
    assigned_resource_id = Column(String, nullable=True)
    resource_type = Column(String, nullable=True)

class ServiceExecution(BaseModel):
    __tablename__ = 'service_execution'
    __table_args__ = {'schema': 'canonical'}
    service_assignment_id = Column(ForeignKey('canonical.service_assignment.id'), nullable=False)
    served_time = Column(DateTime(timezone=True), nullable=True)
    execution_status = Column(String, nullable=True)

class Delay(BaseModel):
    __tablename__ = 'delay'
    __table_args__ = {'schema': 'canonical'}
    vessel_call_id = Column(ForeignKey('canonical.vessel_call.id'), nullable=False)
    movement_stage = Column(String, nullable=False)
    total_duration_hours = Column(Float, nullable=False)
    is_early_service = Column(Boolean, default=False)

class DelayAllocation(BaseModel):
    __tablename__ = 'delay_allocation'
    __table_args__ = {'schema': 'canonical'}
    delay_id = Column(ForeignKey('canonical.delay.id'), nullable=False)
    cause = Column(String, nullable=False)
    duration_hours = Column(Float, nullable=False)
    is_primary = Column(Boolean, default=True)
    cause_status = Column(String, nullable=True) # CONFIRMED|INFERRED
    inference_evidence = Column(JSON, nullable=True)
""")

# config.py
with open(os.path.join(models_dir, "config.py"), "w") as f:
    f.write("""from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from .base import BaseModel

class EventDefinition(BaseModel):
    __tablename__ = 'event_definition'
    __table_args__ = {'schema': 'config'}
    name = Column(String, nullable=False, unique=True)
    category = Column(String, nullable=True)
    description = Column(String, nullable=True)

class EventAlias(BaseModel):
    __tablename__ = 'event_alias'
    __table_args__ = {'schema': 'config'}
    event_definition_id = Column(ForeignKey('config.event_definition.id'), nullable=False)
    alias = Column(String, nullable=False)
    match_type = Column(String, nullable=False) # EXACT|CASE_INSENSITIVE|NORMALISED|REGEX|AI_SUGGESTED
    confirmation_state = Column(String, nullable=True)
""")

# quality.py
with open(os.path.join(models_dir, "quality.py"), "w") as f:
    f.write("""from sqlalchemy import Column, String, Boolean, ForeignKey, JSON, DateTime
from sqlalchemy.orm import relationship
from .base import BaseModel

class QualityRule(BaseModel):
    __tablename__ = 'quality_rule'
    __table_args__ = {'schema': 'quality'}
    rule_id = Column(String, nullable=False, unique=True)
    scope = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    pass_fail_expression = Column(String, nullable=False)
    remediation_guidance = Column(String, nullable=True)
    effective_from = Column(DateTime(timezone=True), nullable=True)
    effective_to = Column(DateTime(timezone=True), nullable=True)

class QualityIssue(BaseModel):
    __tablename__ = 'quality_issue'
    __table_args__ = {'schema': 'quality'}
    rule_id = Column(ForeignKey('quality.quality_rule.id'), nullable=False)
    vessel_call_id = Column(ForeignKey('canonical.vessel_call.id'), nullable=True)
    record_reference = Column(String, nullable=False)
    issue_status = Column(String, nullable=False) # OPEN|RESOLVED|QUARANTINED

class ResolutionDecision(BaseModel):
    __tablename__ = 'resolution_decision'
    __table_args__ = {'schema': 'quality'}
    quality_issue_id = Column(ForeignKey('quality.quality_issue.id'), nullable=False)
    decision = Column(String, nullable=False)
    notes = Column(String, nullable=True)
""")

# identity.py
with open(os.path.join(models_dir, "identity.py"), "w") as f:
    f.write("""from sqlalchemy import Column, String, Float, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from .base import BaseModel

class MatchCandidate(BaseModel):
    __tablename__ = 'match_candidate'
    __table_args__ = {'schema': 'identity'}
    source_record_1_id = Column(String, nullable=False)
    source_record_2_id = Column(String, nullable=False)
    match_score = Column(Float, nullable=False)
    status = Column(String, nullable=False)

class MatchEvidence(BaseModel):
    __tablename__ = 'match_evidence'
    __table_args__ = {'schema': 'identity'}
    match_candidate_id = Column(ForeignKey('identity.match_candidate.id'), nullable=False)
    evidence_type = Column(String, nullable=False)
    evidence_detail = Column(JSON, nullable=False)

class MergeDecision(BaseModel):
    __tablename__ = 'merge_decision'
    __table_args__ = {'schema': 'identity'}
    match_candidate_id = Column(ForeignKey('identity.match_candidate.id'), nullable=False)
    decision = Column(String, nullable=False) # MERGED|REJECTED
    is_reversible = Column(Boolean, default=True)
""")

# journey.py
with open(os.path.join(models_dir, "journey.py"), "w") as f:
    f.write("""from sqlalchemy import Column, String, Integer, ForeignKey, JSON
from sqlalchemy.orm import relationship
from .base import BaseModel

class JourneyTemplate(BaseModel):
    __tablename__ = 'journey_template'
    __table_args__ = {'schema': 'journey'}
    name = Column(String, nullable=False, unique=True)
    dag_definition = Column(JSON, nullable=False)

class JourneyStage(BaseModel):
    __tablename__ = 'journey_stage'
    __table_args__ = {'schema': 'journey'}
    template_id = Column(ForeignKey('journey.journey_template.id'), nullable=False)
    stage_name = Column(String, nullable=False)

class JourneyInstance(BaseModel):
    __tablename__ = 'journey_instance'
    __table_args__ = {'schema': 'journey'}
    vessel_call_id = Column(ForeignKey('canonical.vessel_call.id'), nullable=False)
    template_id = Column(ForeignKey('journey.journey_template.id'), nullable=False)
    status = Column(String, nullable=False)

class StageOccurrence(BaseModel):
    __tablename__ = 'stage_occurrence'
    __table_args__ = {'schema': 'journey'}
    journey_instance_id = Column(ForeignKey('journey.journey_instance.id'), nullable=False)
    stage_id = Column(ForeignKey('journey.journey_stage.id'), nullable=False)
    status = Column(String, nullable=False)

class Handover(BaseModel):
    __tablename__ = 'handover'
    __table_args__ = {'schema': 'journey'}
    from_stage_occurrence_id = Column(ForeignKey('journey.stage_occurrence.id'), nullable=False)
    to_stage_occurrence_id = Column(ForeignKey('journey.stage_occurrence.id'), nullable=False)
    status = Column(String, nullable=False)
""")

# analytics.py
with open(os.path.join(models_dir, "analytics.py"), "w") as f:
    f.write("""from sqlalchemy import Column, String, Float, ForeignKey, JSON, DateTime
from sqlalchemy.orm import relationship
from .base import BaseModel

class LeadTimeDefinition(BaseModel):
    __tablename__ = 'lead_time_definition'
    __table_args__ = {'schema': 'analytics'}
    name = Column(String, nullable=False, unique=True)
    start_event = Column(String, nullable=False)
    end_event = Column(String, nullable=False)

class LeadTimeResult(BaseModel):
    __tablename__ = 'lead_time_result'
    __table_args__ = {'schema': 'analytics'}
    vessel_call_id = Column(ForeignKey('canonical.vessel_call.id'), nullable=False)
    definition_id = Column(ForeignKey('analytics.lead_time_definition.id'), nullable=False)
    duration_hours = Column(Float, nullable=True)

class KPI(BaseModel):
    __tablename__ = 'kpi'
    __table_args__ = {'schema': 'analytics'}
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)

class KPIFormulaVersion(BaseModel):
    __tablename__ = 'kpi_formula_version'
    __table_args__ = {'schema': 'analytics'}
    kpi_id = Column(ForeignKey('analytics.kpi.id'), nullable=False)
    version = Column(String, nullable=False)
    expression = Column(String, nullable=False)

class KPIResult(BaseModel):
    __tablename__ = 'kpi_result'
    __table_args__ = {'schema': 'analytics'}
    kpi_id = Column(ForeignKey('analytics.kpi.id'), nullable=False)
    vessel_call_id = Column(ForeignKey('canonical.vessel_call.id'), nullable=True)
    value = Column(Float, nullable=True)
    status = Column(String, nullable=False) # OK|UNAVAILABLE|NO_SOURCE_DATA
""")

# audit.py
with open(os.path.join(models_dir, "audit.py"), "w") as f:
    f.write("""from sqlalchemy import Column, String, JSON
from .base import BaseModel

class AuditEvent(BaseModel):
    __tablename__ = 'audit_event'
    __table_args__ = {'schema': 'audit'}
    entity_name = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    action = Column(String, nullable=False)
    changes = Column(JSON, nullable=False)
""")

# testkit.py
with open(os.path.join(models_dir, "testkit.py"), "w") as f:
    f.write("""from sqlalchemy import Column, String, Float, Boolean, JSON
from .base import BaseModel

class ExpectedOutput(BaseModel):
    __tablename__ = 'expected_output'
    __table_args__ = {'schema': 'testkit'}
    vcn = Column(String, nullable=False)
    metric_name = Column(String, nullable=False)
    expected_value = Column(Float, nullable=True)

class DQCase(BaseModel):
    __tablename__ = 'dq_case'
    __table_args__ = {'schema': 'testkit'}
    case_id = Column(String, nullable=False)
    description = Column(String, nullable=True)
    expected_outcome = Column(String, nullable=False)
""")

# __init__.py
with open(os.path.join(models_dir, "__init__.py"), "w") as f:
    f.write("""from .base import Base
from .canonical import *
from .config import *
from .quality import *
from .identity import *
from .journey import *
from .analytics import *
from .audit import *
from .testkit import *
""")

print("Models generated in", models_dir)
