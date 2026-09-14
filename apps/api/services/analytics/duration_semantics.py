"""Governed Duration Semantics (spec §10.1, phase-07-analytics.md §1).

Implements each of the 9 duration concepts as a distinct, named, separately tested concept.
Conflating any two of them is explicitly prevented.

1. Lead Time: end actual − start actual
2. Planning Lead Time: requested service time − request submission time
3. Scheduling Gap: scheduled time − requested time
4. Execution Delay: actual service time − scheduled time
5. Target Variance: actual − target
6. Waiting Time: inactive interval awaiting prerequisite/resource/clearance
7. Service Time: interval during which service is actively executed
8. Delay Frequency: delayed eligible events / total eligible events
9. Early Delivery: negative execution delay (preserved with sign)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class SemanticDurationResult:
    concept: str
    status: str  # "AVAILABLE" | "UNAVAILABLE"
    value_hours: Optional[float]
    unit: str = "hours"
    formula_version: str = "1.0"
    unavailable_reason: Optional[str] = None
    is_early_delivery: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


def compute_lead_time(
    start_actual: Optional[datetime],
    end_actual: Optional[datetime],
    formula_version: str = "1.0",
) -> SemanticDurationResult:
    """Lead Time = end actual − start actual (elapsed duration between two observed events)."""
    if start_actual is None or end_actual is None:
        missing = "start_actual" if start_actual is None else "end_actual"
        return SemanticDurationResult(
            concept="Lead Time",
            status="UNAVAILABLE",
            value_hours=None,
            unavailable_reason=f"Missing required timestamp: {missing}",
            formula_version=formula_version,
        )

    delta = (end_actual - start_actual).total_seconds() / 3600.0
    return SemanticDurationResult(
        concept="Lead Time",
        status="AVAILABLE",
        value_hours=round(delta, 6),
        formula_version=formula_version,
    )


def compute_planning_lead_time(
    submission_time: Optional[datetime],
    requested_service_time: Optional[datetime],
    formula_version: str = "1.0",
) -> SemanticDurationResult:
    """Planning Lead Time = requested service time − request submission time."""
    if submission_time is None or requested_service_time is None:
        missing = "submission_time" if submission_time is None else "requested_service_time"
        return SemanticDurationResult(
            concept="Planning Lead Time",
            status="UNAVAILABLE",
            value_hours=None,
            unavailable_reason=f"Missing timestamp for Planning Lead Time: {missing}",
            formula_version=formula_version,
        )

    delta = (requested_service_time - submission_time).total_seconds() / 3600.0
    return SemanticDurationResult(
        concept="Planning Lead Time",
        status="AVAILABLE",
        value_hours=round(delta, 6),
        formula_version=formula_version,
    )


def compute_scheduling_gap(
    requested_service_time: Optional[datetime],
    scheduled_time: Optional[datetime],
    formula_version: str = "1.0",
) -> SemanticDurationResult:
    """Scheduling Gap = scheduled time − requested time (lag in port resource allocation)."""
    if requested_service_time is None or scheduled_time is None:
        missing = "requested_service_time" if requested_service_time is None else "scheduled_time"
        return SemanticDurationResult(
            concept="Scheduling Gap",
            status="UNAVAILABLE",
            value_hours=None,
            unavailable_reason=f"Missing timestamp for Scheduling Gap: {missing}",
            formula_version=formula_version,
        )

    delta = (scheduled_time - requested_service_time).total_seconds() / 3600.0
    return SemanticDurationResult(
        concept="Scheduling Gap",
        status="AVAILABLE",
        value_hours=round(delta, 6),
        formula_version=formula_version,
    )


def compute_execution_delay(
    scheduled_time: Optional[datetime],
    served_time: Optional[datetime],
    formula_version: str = "1.0",
) -> SemanticDurationResult:
    """Execution Delay = actual service time − scheduled time.

    Negative values represent valid early service delivery (spec §2.4, AGENTS.md §3.4).
    """
    if scheduled_time is None or served_time is None:
        missing = "scheduled_time" if scheduled_time is None else "served_time"
        return SemanticDurationResult(
            concept="Execution Delay",
            status="UNAVAILABLE",
            value_hours=None,
            unavailable_reason=f"Missing timestamp for Execution Delay: {missing}",
            formula_version=formula_version,
        )

    delta = (served_time - scheduled_time).total_seconds() / 3600.0
    val = round(delta, 6)
    return SemanticDurationResult(
        concept="Execution Delay",
        status="AVAILABLE",
        value_hours=val,
        is_early_delivery=(val < 0),
        formula_version=formula_version,
    )


def compute_target_variance(
    actual_value: Optional[float],
    target_value: Optional[float],
    formula_version: str = "1.0",
) -> SemanticDurationResult:
    """Target Variance = actual − target."""
    if actual_value is None or target_value is None:
        missing = "actual_value" if actual_value is None else "target_value"
        return SemanticDurationResult(
            concept="Target Variance",
            status="UNAVAILABLE",
            value_hours=None,
            unavailable_reason=f"Missing input for Target Variance: {missing}",
            formula_version=formula_version,
        )

    variance = round(actual_value - target_value, 6)
    return SemanticDurationResult(
        concept="Target Variance",
        status="AVAILABLE",
        value_hours=variance,
        formula_version=formula_version,
    )


def compute_waiting_time(
    stages: List[Dict[str, Any]],
    formula_version: str = "1.0",
) -> SemanticDurationResult:
    """Waiting Time = sum of durations for stages categorized as PASSIVE_WAIT or HOLD."""
    total_wait = 0.0
    has_valid_stage = False

    for st in stages:
        cat = st.get("time_category", "")
        dur = st.get("duration_hours")
        if cat in ("PASSIVE_WAIT", "HOLD", "WAITING") and dur is not None:
            total_wait += dur
            has_valid_stage = True

    if not has_valid_stage:
        return SemanticDurationResult(
            concept="Waiting Time",
            status="UNAVAILABLE",
            value_hours=None,
            unavailable_reason="No available waiting stages in timeline",
            formula_version=formula_version,
        )

    return SemanticDurationResult(
        concept="Waiting Time",
        status="AVAILABLE",
        value_hours=round(total_wait, 6),
        formula_version=formula_version,
    )


def compute_service_time(
    stages: List[Dict[str, Any]],
    formula_version: str = "1.0",
) -> SemanticDurationResult:
    """Service Time = sum of durations for stages categorized as ACTIVE_SERVICE."""
    total_service = 0.0
    has_valid_stage = False

    for st in stages:
        cat = st.get("time_category", "")
        dur = st.get("duration_hours")
        if cat in ("ACTIVE_SERVICE", "SERVICE") and dur is not None:
            total_service += dur
            has_valid_stage = True

    if not has_valid_stage:
        return SemanticDurationResult(
            concept="Service Time",
            status="UNAVAILABLE",
            value_hours=None,
            unavailable_reason="No available active service stages in timeline",
            formula_version=formula_version,
        )

    return SemanticDurationResult(
        concept="Service Time",
        status="AVAILABLE",
        value_hours=round(total_service, 6),
        formula_version=formula_version,
    )


def compute_delay_frequency(
    delayed_event_count: int,
    total_eligible_event_count: int,
    formula_version: str = "1.0",
) -> SemanticDurationResult:
    """Delay Frequency = delayed eligible events / total eligible events."""
    if total_eligible_event_count <= 0:
        return SemanticDurationResult(
            concept="Delay Frequency",
            status="UNAVAILABLE",
            value_hours=None,
            unit="ratio",
            unavailable_reason="Total eligible events must be greater than zero",
            formula_version=formula_version,
        )

    freq = round(delayed_event_count / total_eligible_event_count, 4)
    return SemanticDurationResult(
        concept="Delay Frequency",
        status="AVAILABLE",
        value_hours=freq,
        unit="ratio",
        formula_version=formula_version,
    )


def compute_early_delivery(
    execution_delay: Optional[float],
    formula_version: str = "1.0",
) -> SemanticDurationResult:
    """Early Delivery = negative execution delay (preserves negative sign as early service)."""
    if execution_delay is None:
        return SemanticDurationResult(
            concept="Early Delivery",
            status="UNAVAILABLE",
            value_hours=None,
            unavailable_reason="Execution delay is unavailable",
            formula_version=formula_version,
        )

    is_early = execution_delay < 0
    return SemanticDurationResult(
        concept="Early Delivery",
        status="AVAILABLE",
        value_hours=execution_delay if is_early else 0.0,
        is_early_delivery=is_early,
        formula_version=formula_version,
        metadata={"early_hours": abs(execution_delay) if is_early else 0.0},
    )
