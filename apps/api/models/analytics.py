from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, JSON, String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from .base import BaseModel


class LeadTimeDefinition(BaseModel):
    __tablename__ = "lead_time_definition"
    __table_args__ = {"schema": "analytics"}
    name = Column(String, nullable=False, unique=True)
    start_event = Column(String, nullable=False)
    end_event = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    formula_version = Column(String, nullable=False, default="1.0")
    unit = Column(String, nullable=False, default="hours")
    eligibility_criteria = Column(JSON, nullable=True)
    null_handling = Column(String, nullable=False, default="UNAVAILABLE")
    occurrence_selection = Column(String, nullable=False, default="first")
    # COMPUTABLE | NO_SOURCE_DATA
    availability_status = Column(String, nullable=False, default="COMPUTABLE")
    required_events = Column(JSON, nullable=True)
    custom_builder = Column(Boolean, nullable=False, default=False)
    created_by_user = Column(String, nullable=True)
    # True when the metric uses service execution records (not event occurrences)
    is_execution_delay = Column(Boolean, nullable=False, default=False)
    # Arrival | Sailing — only used when is_execution_delay=True
    execution_delay_movement = Column(String, nullable=True)


class LeadTimeResult(BaseModel):
    __tablename__ = "lead_time_result"
    __table_args__ = {"schema": "analytics"}
    vessel_call_id = Column(ForeignKey("canonical.vessel_call.id"), nullable=False)
    definition_id = Column(ForeignKey("analytics.lead_time_definition.id"), nullable=False)
    vcn = Column(String, nullable=True)
    duration_hours = Column(Float, nullable=True)

    # Traceability envelope (spec §2, phase-07-analytics.md §5)
    status = Column(String, nullable=False, default="UNAVAILABLE")  # AVAILABLE | UNAVAILABLE | NO_SOURCE_DATA
    unavailable_reason = Column(Text, nullable=True)
    formula_version = Column(String, nullable=True)
    source_record_ids = Column(JSON, nullable=True)      # list of UUID strings
    filter_context = Column(JSON, nullable=True)
    exclusions_applied = Column(JSON, nullable=True)
    dq_status = Column(String, nullable=True)            # CLEAN | DQ_ISSUES
    calculated_at = Column(DateTime(timezone=True), nullable=True)

    # Event occurrence references for drill-through
    start_event_occurrence_id = Column(ForeignKey("canonical.event_occurrence.id", ondelete="SET NULL"), nullable=True)
    end_event_occurrence_id = Column(ForeignKey("canonical.event_occurrence.id", ondelete="SET NULL"), nullable=True)
    start_time = Column(DateTime(timezone=True), nullable=True)
    end_time = Column(DateTime(timezone=True), nullable=True)


class StatisticalAggregate(BaseModel):
    """
    Aggregate statistics for a lead-time definition over a cohort.
    Percentile method: linear interpolation (disclosed in percentile_method column).
    """
    __tablename__ = "statistical_aggregate"
    __table_args__ = {"schema": "analytics"}
    definition_id = Column(ForeignKey("analytics.lead_time_definition.id"), nullable=False)
    cohort_key = Column(String, nullable=False, default="all")
    cohort_filters = Column(JSON, nullable=True)

    observation_count = Column(Integer, nullable=True)
    missing_count = Column(Integer, nullable=True)
    mean_hours = Column(Float, nullable=True)
    median_hours = Column(Float, nullable=True)
    std_hours = Column(Float, nullable=True)
    cv = Column(Float, nullable=True)                  # σ/μ, None when |μ| < 0.001
    min_hours = Column(Float, nullable=True)
    max_hours = Column(Float, nullable=True)
    p25_hours = Column(Float, nullable=True)
    p75_hours = Column(Float, nullable=True)
    p90_hours = Column(Float, nullable=True)
    p95_hours = Column(Float, nullable=True)
    fastest_vcn = Column(String, nullable=True)
    slowest_vcn = Column(String, nullable=True)
    tail_risk_ratio = Column(Float, nullable=True)     # P90 / median; None when median <= 0
    right_skew_flag = Column(Boolean, nullable=True)
    percentile_method = Column(String, nullable=False, default="linear_interpolation")
    small_sample_warning = Column(Boolean, nullable=False, default=False)
    outlier_vcns = Column(JSON, nullable=True)
    formula_version = Column(String, nullable=True)
    quarantine_excluded = Column(Boolean, nullable=False, default=True)
    calculated_at = Column(DateTime(timezone=True), nullable=True)


class KPI(BaseModel):
    __tablename__ = "kpi"
    __table_args__ = {"schema": "analytics"}
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)


class KPIFormulaVersion(BaseModel):
    __tablename__ = "kpi_formula_version"
    __table_args__ = {"schema": "analytics"}
    kpi_id = Column(ForeignKey("analytics.kpi.id"), nullable=False)
    version = Column(String, nullable=False)
    expression = Column(String, nullable=False)


class KPIResult(BaseModel):
    __tablename__ = "kpi_result"
    __table_args__ = {"schema": "analytics"}
    kpi_id = Column(ForeignKey("analytics.kpi.id"), nullable=False)
    vessel_call_id = Column(ForeignKey("canonical.vessel_call.id"), nullable=True)
    value = Column(Float, nullable=True)
    status = Column(String, nullable=False)  # OK|UNAVAILABLE|NO_SOURCE_DATA
