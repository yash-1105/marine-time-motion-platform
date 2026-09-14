"""Time and motion analytics module (Phase 07)."""

from .catalogue import ensure_catalogue
from .custom_builder import CustomLeadTimeBuilder
from .duration_semantics import (
    SemanticDurationResult,
    compute_delay_frequency,
    compute_early_delivery,
    compute_execution_delay,
    compute_lead_time,
    compute_planning_lead_time,
    compute_scheduling_gap,
    compute_service_time,
    compute_target_variance,
    compute_waiting_time,
)
from .engine import AnalyticsEngine, within_tolerance

__all__ = [
    "ensure_catalogue",
    "AnalyticsEngine",
    "CustomLeadTimeBuilder",
    "within_tolerance",
    "SemanticDurationResult",
    "compute_lead_time",
    "compute_planning_lead_time",
    "compute_scheduling_gap",
    "compute_execution_delay",
    "compute_target_variance",
    "compute_waiting_time",
    "compute_service_time",
    "compute_delay_frequency",
    "compute_early_delivery",
]
