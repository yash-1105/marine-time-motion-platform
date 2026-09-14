from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)

from .base import BaseModel


class JourneyTemplate(BaseModel):
    __tablename__ = "journey_template"
    __table_args__ = {"schema": "journey"}
    name = Column(String, nullable=False, unique=True)
    rule_version = Column(String, nullable=False, default="1.0")
    dag_definition = Column(JSON, nullable=False)


class JourneyStage(BaseModel):
    """Catalogue of stages defined by a template (the standard path)."""

    __tablename__ = "journey_stage"
    __table_args__ = {"schema": "journey"}
    template_id = Column(ForeignKey("journey.journey_template.id"), nullable=False)
    stage_name = Column(String, nullable=False)
    sequence_index = Column(Integer, nullable=False, default=0)
    start_event_name = Column(String, nullable=True)
    end_event_name = Column(String, nullable=True)
    time_category = Column(String, nullable=False, default="UNCLASSIFIED")
    # ACTIVE_SERVICE | PASSIVE_WAIT | HOLD | DELAY | UNCLASSIFIED
    actor_from = Column(String, nullable=True)
    actor_to = Column(String, nullable=True)
    is_optional = Column(Boolean, default=False, nullable=False)
    is_repeatable = Column(Boolean, default=False, nullable=False)


class JourneyInstance(BaseModel):
    """One reconstructed journey for one vessel call."""

    __tablename__ = "journey_instance"
    __table_args__ = {"schema": "journey"}
    vessel_call_id = Column(ForeignKey("canonical.vessel_call.id"), nullable=False, unique=True)
    template_id = Column(ForeignKey("journey.journey_template.id"), nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    # RECONSTRUCTED | PARTIAL | FAILED

    reconstruction_version = Column(Integer, nullable=False, default=1)
    rule_version = Column(String, nullable=True)
    computed_at = Column(DateTime(timezone=True), nullable=True)

    coverage_summary = Column(JSON, nullable=True)
    # {"stages_total": n, "stages_available": n, "stages_missing": n, "stages_inferred": n}
    time_decomposition = Column(JSON, nullable=True)
    # {"ACTIVE_SERVICE": h, "PASSIVE_WAIT": h, "HOLD": h, "DELAY": h, "UNCLASSIFIED": h, "total_hours": h}
    deviation_report = Column(JSON, nullable=True)
    # list of {"type": ..., "stage": ..., "description": ..., "severity": ...}


class StageOccurrence(BaseModel):
    """A concrete occurrence of a stage within one journey instance."""

    __tablename__ = "stage_occurrence"
    __table_args__ = {"schema": "journey"}
    journey_instance_id = Column(ForeignKey("journey.journey_instance.id"), nullable=False)
    stage_id = Column(ForeignKey("journey.journey_stage.id"), nullable=False)
    stage_name = Column(String, nullable=False)
    sequence_index = Column(Integer, nullable=False, default=0)
    shift_occurrence_index = Column(Integer, nullable=False, default=0)  # 0 = not repeated, 1..n for shifting

    start_event_occurrence_id = Column(ForeignKey("canonical.event_occurrence.id"), nullable=True)
    end_event_occurrence_id = Column(ForeignKey("canonical.event_occurrence.id"), nullable=True)
    start_time = Column(DateTime(timezone=True), nullable=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    duration_hours = Column(Float, nullable=True)

    availability = Column(String, nullable=False, default="UNAVAILABLE")  # AVAILABLE | UNAVAILABLE
    is_missing = Column(Boolean, default=False, nullable=False)
    is_inferred = Column(Boolean, default=False, nullable=False)
    inference_reason = Column(String, nullable=True)

    time_category = Column(String, nullable=False, default="UNCLASSIFIED")
    status = Column(String, nullable=False, default="PENDING")  # AVAILABLE|MISSING|INFERRED|DEVIATED

    deviation_type = Column(String, nullable=True)
    deviation_detail = Column(JSON, nullable=True)


class Handover(BaseModel):
    """A stakeholder-to-stakeholder handover between two consecutive stage occurrences."""

    __tablename__ = "handover"
    __table_args__ = {"schema": "journey"}
    from_stage_occurrence_id = Column(ForeignKey("journey.stage_occurrence.id"), nullable=False)
    to_stage_occurrence_id = Column(ForeignKey("journey.stage_occurrence.id"), nullable=False)
    status = Column(String, nullable=False, default="UNAVAILABLE")  # AVAILABLE|UNAVAILABLE

    from_actor = Column(String, nullable=True)
    to_actor = Column(String, nullable=True)
    handover_time = Column(DateTime(timezone=True), nullable=True)
    wait_duration_hours = Column(Float, nullable=True)


class CanonicalObservation(BaseModel):
    """
    Records the canonical-occurrence-selection decision for a logical event slot
    (a vessel call + event definition) where multiple source records observed it.
    Never deletes conflicting observations; only records which one governs.
    """

    __tablename__ = "canonical_observation"
    __table_args__ = {"schema": "journey"}
    vessel_call_id = Column(ForeignKey("canonical.vessel_call.id"), nullable=False)
    event_definition_id = Column(ForeignKey("config.event_definition.id"), nullable=False)

    candidate_event_occurrence_ids = Column(JSON, nullable=False)  # all observations considered
    selected_event_occurrence_id = Column(ForeignKey("canonical.event_occurrence.id"), nullable=True)

    conflict_detected = Column(Boolean, default=False, nullable=False)
    selection_method = Column(String, nullable=False, default="AUTOMATIC")  # AUTOMATIC|STEWARD_OVERRIDE
    selection_reasoning = Column(JSON, nullable=True)
    quality_issue_id = Column(ForeignKey("quality.quality_issue.id"), nullable=True)

    decided_by = Column(String, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    rule_version = Column(String, nullable=True)


class ObservationCorrection(BaseModel):
    """
    A steward correction. Never mutates raw or the prior canonical value: it creates a new
    canonical EventOccurrence, marks the prior one superseded, and requires approval.
    """

    __tablename__ = "observation_correction"
    __table_args__ = {"schema": "journey"}
    vessel_call_id = Column(ForeignKey("canonical.vessel_call.id"), nullable=False)
    event_definition_id = Column(ForeignKey("config.event_definition.id"), nullable=True)

    prior_event_occurrence_id = Column(ForeignKey("canonical.event_occurrence.id"), nullable=True)
    new_event_occurrence_id = Column(ForeignKey("canonical.event_occurrence.id"), nullable=True)

    reason = Column(String, nullable=False)
    actor = Column(String, nullable=False)
    approval_state = Column(String, nullable=False, default="PENDING")  # PENDING|APPROVED|REJECTED
    approved_by = Column(String, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    triggers_recalculation = Column(Boolean, default=True, nullable=False)
    recalculated_at = Column(DateTime(timezone=True), nullable=True)


class JourneyNarrative(BaseModel):
    """AI-generated factual per-vessel-call narrative, grounded strictly in the reconstructed record."""

    __tablename__ = "journey_narrative"
    __table_args__ = {"schema": "journey"}
    vessel_call_id = Column(ForeignKey("canonical.vessel_call.id"), nullable=False)
    journey_instance_id = Column(ForeignKey("journey.journey_instance.id"), nullable=False)

    narrative_text = Column(String, nullable=False)
    grounding_record_ids = Column(JSON, nullable=False)
    model_name = Column(String, nullable=False)
    is_ai_generated = Column(Boolean, default=True, nullable=False)
    inference_status = Column(String, nullable=False, default="AI_GENERATED")
    generated_at = Column(DateTime(timezone=True), nullable=True)


class ReconstructionHistory(BaseModel):
    """Versioned snapshot of a journey instance's reconstruction, retained across re-runs."""

    __tablename__ = "reconstruction_history"
    __table_args__ = {"schema": "journey"}
    journey_instance_id = Column(ForeignKey("journey.journey_instance.id"), nullable=False)
    vessel_call_id = Column(ForeignKey("canonical.vessel_call.id"), nullable=False)
    run_version = Column(Integer, nullable=False)
    rule_version = Column(String, nullable=True)
    triggered_by = Column(String, nullable=False, default="SYSTEM")  # SYSTEM|CORRECTION|MANUAL
    snapshot = Column(JSON, nullable=False)
