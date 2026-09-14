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
    kpi_number = Column(Integer, nullable=True)
    code = Column(String(50), nullable=True, index=True)
    category = Column(String(100), nullable=True)
    formula = Column(Text, nullable=True)
    numerator = Column(Text, nullable=True)
    denominator = Column(Text, nullable=True)
    unit = Column(String(50), nullable=True)
    eligible_population = Column(Text, nullable=True)
    required_events = Column(JSON, nullable=True)
    required_fields = Column(JSON, nullable=True)
    exclusions = Column(JSON, nullable=True)
    aggregation_method = Column(String(50), nullable=False, default="AVG")
    vessel_applicability = Column(String(100), nullable=False, default="All")
    target = Column(Float, nullable=True)
    target_direction = Column(String(20), nullable=True, default="LOWER_IS_BETTER")
    thresholds = Column(JSON, nullable=True)
    owner = Column(String(100), nullable=True)
    effective_from = Column(DateTime(timezone=True), nullable=True)
    effective_to = Column(DateTime(timezone=True), nullable=True)
    is_primary = Column(Boolean, nullable=False, default=True)
    alias_of_id = Column(ForeignKey("analytics.kpi.id", ondelete="SET NULL"), nullable=True)
    availability_status = Column(String(50), nullable=False, default="COMPUTED")
    required_source_systems = Column(JSON, nullable=True)


class KPIFormulaVersion(BaseModel):
    __tablename__ = "kpi_formula_version"
    __table_args__ = {"schema": "analytics"}

    kpi_id = Column(ForeignKey("analytics.kpi.id", ondelete="CASCADE"), nullable=False)
    version = Column(String, nullable=False)
    expression = Column(String, nullable=False)


class KPIResult(BaseModel):
    __tablename__ = "kpi_result"
    __table_args__ = {"schema": "analytics"}

    kpi_id = Column(ForeignKey("analytics.kpi.id", ondelete="CASCADE"), nullable=False)
    vessel_call_id = Column(ForeignKey("canonical.vessel_call.id", ondelete="CASCADE"), nullable=True)
    value = Column(Float, nullable=True)
    status = Column(String, nullable=False)  # COMPUTED | UNAVAILABLE | NO_SOURCE_DATA
    period_start = Column(DateTime(timezone=True), nullable=True)
    period_end = Column(DateTime(timezone=True), nullable=True)
    grain = Column(String(20), nullable=True, default="ALL")
    cohort_key = Column(String(100), nullable=True, default="all")
    cohort_filters = Column(JSON, nullable=True)
    numerator_value = Column(Float, nullable=True)
    denominator_value = Column(Float, nullable=True)
    target_value = Column(Float, nullable=True)
    band = Column(String(20), nullable=True)  # GREEN | AMBER | RED | GRAY
    unavailable_reason = Column(Text, nullable=True)
    formula_version = Column(String(50), nullable=True, default="1.0")
    data_quality_summary = Column(JSON, nullable=True)
    calculated_at = Column(DateTime(timezone=True), nullable=True)
    is_recalculation = Column(Boolean, nullable=False, default=False)


class KPIBenchmark(BaseModel):
    __tablename__ = "kpi_benchmark"
    __table_args__ = {"schema": "analytics"}

    kpi_id = Column(ForeignKey("analytics.kpi.id", ondelete="CASCADE"), nullable=False)
    peer_port = Column(String(100), nullable=False)
    benchmark_value = Column(Float, nullable=False)
    source = Column(String(255), nullable=True)
    period = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)


class BottleneckRecord(BaseModel):
    __tablename__ = "bottleneck_record"
    __table_args__ = {"schema": "analytics"}

    stage_or_resource = Column(String(100), nullable=False)
    bottleneck_type = Column(String(50), nullable=False)  # RESOURCE_BOTTLENECK | PROCESS_BOTTLENECK
    duration_score = Column(Float, nullable=False)
    frequency_score = Column(Float, nullable=False)
    variability_score = Column(Float, nullable=False)
    tail_risk_score = Column(Float, nullable=False)
    turnaround_contribution = Column(Float, nullable=False)
    repeated_target_breach_rate = Column(Float, nullable=False)
    business_criticality_score = Column(Float, nullable=False)
    overall_bottleneck_score = Column(Float, nullable=False)
    rank = Column(Integer, nullable=False)
    details = Column(JSON, nullable=True)


class OutlierRecord(BaseModel):
    __tablename__ = "outlier_record"
    __table_args__ = {"schema": "analytics"}

    vessel_call_id = Column(ForeignKey("canonical.vessel_call.id", ondelete="CASCADE"), nullable=False)
    vcn = Column(String(100), nullable=False)
    outlier_type = Column(String(100), nullable=False)  # OPERATIONAL_OUTLIER | DATA_QUALITY_OUTLIER | PROCESS_VIOLATION | EXTREME_DELAY_CASE | HIGH_CRITICALITY_CASE
    metric_name = Column(String(100), nullable=False)
    observed_value = Column(Float, nullable=False)
    benchmark_or_p90 = Column(Float, nullable=True)
    divergence = Column(Float, nullable=True)
    is_excluded_from_kpi = Column(Boolean, default=False)
    exclusion_rationale = Column(Text, nullable=True)
    severity = Column(String(20), default="MEDIUM")
    evidence = Column(JSON, nullable=True)
    detected_at = Column(DateTime(timezone=True), nullable=True)


class AlertRule(BaseModel):
    __tablename__ = "alert_rule"
    __table_args__ = {"schema": "analytics"}

    rule_code = Column(String(100), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)  # SLA | BOTTLENECK | OUTLIER | RESOURCE | QUALITY
    severity = Column(String(20), nullable=False)  # INFO | LOW | MEDIUM | HIGH | CRITICAL
    description = Column(Text, nullable=True)
    threshold_config = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    suppression_window_minutes = Column(Integer, default=60)


class OperationalAlert(BaseModel):
    __tablename__ = "operational_alert"
    __table_args__ = {"schema": "analytics"}

    alert_rule_id = Column(ForeignKey("analytics.alert_rule.id", ondelete="SET NULL"), nullable=True)
    rule_code = Column(String(100), nullable=False)
    severity = Column(String(20), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    vessel_call_id = Column(ForeignKey("canonical.vessel_call.id", ondelete="SET NULL"), nullable=True)
    vcn = Column(String(100), nullable=True)
    status = Column(String(50), default="NEW")  # NEW | ACKNOWLEDGED | RESOLVED | SUPPRESSED
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(String(100), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(String(100), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    linked_entity_type = Column(String(100), nullable=True)
    linked_entity_id = Column(String(100), nullable=True)
    evidence = Column(JSON, nullable=True)


class ActionItem(BaseModel):
    __tablename__ = "action_item"
    __table_args__ = {"schema": "analytics"}

    alert_id = Column(ForeignKey("analytics.operational_alert.id", ondelete="SET NULL"), nullable=True)
    vessel_call_id = Column(ForeignKey("canonical.vessel_call.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    assigned_to = Column(String(100), nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(50), default="OPEN")  # OPEN | IN_PROGRESS | COMPLETED | CANCELLED
    priority = Column(String(20), default="MEDIUM")
    comments = Column(JSON, default=list)
    created_by = Column(String(100), nullable=True)

