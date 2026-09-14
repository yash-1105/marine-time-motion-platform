from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from .base import BaseModel


class VesselCall(BaseModel):
    __tablename__ = "vessel_call"
    __table_args__ = {"schema": "canonical"}

    # Master attributes
    vessel_name = Column(String, nullable=False)
    imo_number = Column(String, nullable=True)
    vcn = Column(String, nullable=True)
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

    # Data Scope attributes
    tenant_id = Column(String, nullable=False, default="default-tenant")
    port_id = Column(String, nullable=True)
    terminal_id = Column(String, nullable=True)

    # Identity resolution and merge tracking
    is_merged = Column(Boolean, default=False, nullable=False, index=True)
    merged_into_id = Column(ForeignKey("canonical.vessel_call.id", ondelete="SET NULL"), nullable=True)


class EventOccurrence(BaseModel):
    __tablename__ = "event_occurrence"
    __table_args__ = (
        UniqueConstraint("vessel_call_id", "event_definition_id", "occurrence_index", name="uq_event_occurrence"),
        {"schema": "canonical"},
    )

    vessel_call_id = Column(ForeignKey("canonical.vessel_call.id"), nullable=False)
    event_definition_id = Column(ForeignKey("config.event_definition.id"), nullable=False)
    occurrence_index = Column(Integer, default=1, nullable=False)
    movement_scope = Column(String, nullable=False)  # ARRIVAL|SHIFTING|SAILING

    # Timestamp envelope
    original_string = Column(String, nullable=True)
    parsed_value = Column(DateTime(timezone=True), nullable=True)
    source_timezone = Column(String, nullable=True)
    utc_value = Column(DateTime(timezone=True), nullable=False)
    capture_method = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    verification_status = Column(String, nullable=True)  # Verified|Conflicting|Unverified
    source_system = Column(String, nullable=True)
    source_record_id = Column(String, nullable=True)
    ingestion_batch_id = Column(String, nullable=True)
    correction_history = Column(JSON, nullable=True)

    inference_status = Column(String, nullable=True)
    human_review_state = Column(String, nullable=True)
    is_quarantined = Column(Boolean, default=False)

    # Set when this observation was created by a steward correction (journey.observation_correction)
    superseded_by_id = Column(ForeignKey("canonical.event_occurrence.id", ondelete="SET NULL"), nullable=True)
    is_superseded = Column(Boolean, default=False, nullable=False)


class ServiceRequest(BaseModel):
    __tablename__ = "service_request"
    __table_args__ = {"schema": "canonical"}
    vessel_call_id = Column(ForeignKey("canonical.vessel_call.id"), nullable=False)
    service_type = Column(String, nullable=False)
    requested_time = Column(DateTime(timezone=True), nullable=True)
    # Added Phase 07: movement context for execution delay computation
    movement_type = Column(String, nullable=True)    # Arrival | Sailing | Shifting
    submission_time = Column(DateTime(timezone=True), nullable=True)  # Planning Lead Time numerator


class ServiceAssignment(BaseModel):
    __tablename__ = "service_assignment"
    __table_args__ = {"schema": "canonical"}
    service_request_id = Column(ForeignKey("canonical.service_request.id"), nullable=False)
    scheduled_time = Column(DateTime(timezone=True), nullable=True)
    assigned_resource_id = Column(String, nullable=True)
    resource_type = Column(String, nullable=True)


class ServiceExecution(BaseModel):
    __tablename__ = "service_execution"
    __table_args__ = {"schema": "canonical"}
    service_assignment_id = Column(ForeignKey("canonical.service_assignment.id"), nullable=False)
    served_time = Column(DateTime(timezone=True), nullable=True)
    execution_status = Column(String, nullable=True)


class Delay(BaseModel):
    __tablename__ = "delay"
    __table_args__ = {"schema": "canonical"}
    vessel_call_id = Column(ForeignKey("canonical.vessel_call.id", ondelete="CASCADE"), nullable=False)
    source_delay_id = Column(String(50), nullable=True)
    movement_stage = Column(String, nullable=False)
    total_duration_hours = Column(Float, nullable=False)
    is_early_service = Column(Boolean, default=False)
    scheduled_time = Column(DateTime(timezone=True), nullable=True)
    served_time = Column(DateTime(timezone=True), nullable=True)
    delay_hours = Column(Float, nullable=True)
    recalculated_delay_hours = Column(Float, nullable=True)
    delay_reason = Column(String(255), nullable=True)
    source_category = Column(String(100), nullable=True)
    canonical_category = Column(String(100), nullable=True)
    cause_status = Column(String(50), default="Confirmed")  # Confirmed | Inferred
    confidence = Column(String(50), default="High")
    resolution_status = Column(String(50), default="Open")  # Open | Closed | Under Review | Mitigated
    has_reconciliation_mismatch = Column(Boolean, default=False)
    reconciliation_notes = Column(Text, nullable=True)
    requires_reason_review = Column(Boolean, default=False)


class DelayAllocation(BaseModel):
    __tablename__ = "delay_allocation"
    __table_args__ = {"schema": "canonical"}
    delay_id = Column(ForeignKey("canonical.delay.id", ondelete="CASCADE"), nullable=False)
    cause = Column(String, nullable=False)
    canonical_category = Column(String(100), nullable=True)
    reason = Column(String(255), nullable=True)
    duration_hours = Column(Float, nullable=False)
    is_primary = Column(Boolean, default=True)
    cause_status = Column(String(50), default="CONFIRMED")  # CONFIRMED | INFERRED
    confidence = Column(Float, nullable=True)
    inference_evidence = Column(JSON, nullable=True)
    human_review_state = Column(String(50), default="APPROVED")  # APPROVED | PENDING_REVIEW | REJECTED


class CargoOperation(BaseModel):
    __tablename__ = "cargo_operation"
    __table_args__ = {"schema": "canonical"}

    vessel_call_id = Column(ForeignKey("canonical.vessel_call.id", ondelete="CASCADE"), nullable=False)
    operation_id = Column(String, nullable=True)
    cargo_type = Column(String, nullable=True)
    operation_type = Column(String, nullable=True)
    planned_quantity = Column(Float, nullable=True)
    unit = Column(String, nullable=True)
    cargo_start = Column(DateTime(timezone=True), nullable=True)
    cargo_end = Column(DateTime(timezone=True), nullable=True)
    working_hours = Column(Float, nullable=True)
    resources_deployed = Column(Integer, nullable=True)
    downtime_hours = Column(Float, nullable=True)
    actual_quantity = Column(Float, nullable=True)
    data_status = Column(String, nullable=True)
