"""Time and Motion Analytics REST API (Phase 07, spec §10 & §16).

All routes are protected by the repository-level authorization dependency `require()`.
Every metric response provides complete traceability: formula version, source record IDs,
filter context, exclusions, and data-quality status.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import require
from apps.api.auth.principal import UserPrincipal
from apps.api.core.database import get_db
from apps.api.models.analytics import (
    LeadTimeDefinition,
    LeadTimeResult,
    StatisticalAggregate,
)
from apps.api.models.canonical import VesselCall
from apps.api.services.analytics.catalogue import ensure_catalogue
from apps.api.services.analytics.custom_builder import CustomLeadTimeBuilder
from apps.api.services.analytics.engine import AnalyticsEngine

router = APIRouter(prefix="/analytics", tags=["Time and Motion Analytics"])


class CustomLeadTimeRequest(BaseModel):
    start_event: str = Field(..., description="Canonical start event name")
    end_event: str = Field(..., description="Canonical end event name")
    occurrence_selection: str = Field("first", description="first | last | nth | all")
    occurrence_n: int = Field(1, description="Index when occurrence_selection is nth")
    movement_scope: Optional[str] = Field(None, description="Optional movement scope (ARRIVAL, SAILING, SHIFTING)")
    save_as_name: Optional[str] = Field(None, description="Optional catalogue name to save this custom definition")
    description: Optional[str] = Field(None, description="Description if saving to catalogue")


def _resolve_target_tenant(principal: UserPrincipal, explicit_tenant: Optional[str] = None) -> str:
    if explicit_tenant:
        return explicit_tenant
    if principal.data_scope.tenant_id in ("*", "tenant-synthetic-01"):
        return "synthetic-tenant"
    return principal.data_scope.tenant_id


@router.post("/compute")
def compute_analytics(
    vessel_call_id: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("recalculate", "vessel_call")),
):
    """Computes all governed lead-time metrics and statistical aggregates for the tenant."""
    target_tenant = _resolve_target_tenant(principal, tenant_id)
    engine = AnalyticsEngine(db, tenant_id=target_tenant)
    vc_ids = [vessel_call_id] if vessel_call_id else None
    summary = engine.compute_all_metrics(vessel_call_ids=vc_ids)
    engine.compute_all_statistics()
    return {"status": "success", **summary}


@router.get("/events")
def list_canonical_events(
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "vessel_call")),
):
    """Lists all available canonical event definitions for custom lead-time building."""
    from apps.api.models.config import EventDefinition
    events = db.execute(select(EventDefinition).order_by(EventDefinition.name.asc())).scalars().all()
    return [{"id": str(e.id), "name": e.name, "category": e.category} for e in events]


@router.get("/metrics")
def list_lead_time_definitions(
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "vessel_call")),
):
    """Lists all governed lead-time definitions, including reconciliation targets and NO_SOURCE_DATA items."""
    ensure_catalogue(db)
    definitions = db.execute(
        select(LeadTimeDefinition).order_by(LeadTimeDefinition.availability_status.asc(), LeadTimeDefinition.name.asc())
    ).scalars().all()

    return [
        {
            "id": str(d.id),
            "name": d.name,
            "start_event": d.start_event,
            "end_event": d.end_event,
            "description": d.description,
            "formula_version": d.formula_version,
            "unit": d.unit,
            "null_handling": d.null_handling,
            "occurrence_selection": d.occurrence_selection,
            "availability_status": d.availability_status,
            "required_events": d.required_events,
            "is_execution_delay": d.is_execution_delay,
            "execution_delay_movement": d.execution_delay_movement,
            "custom_builder": d.custom_builder,
        }
        for d in definitions
    ]


@router.get("/metrics/{definition_id}/results")
def get_metric_results(
    definition_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    result_status: Optional[str] = Query(None, alias="status"),
    tenant_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "vessel_call")),
):
    """Returns paginated per-vessel-call calculation results with the complete traceability envelope."""
    defn = db.execute(
        select(LeadTimeDefinition).where(LeadTimeDefinition.id == definition_id)
    ).scalar_one_or_none()
    if not defn:
        raise HTTPException(status_code=404, detail="LeadTimeDefinition not found")

    target_tenant = _resolve_target_tenant(principal, tenant_id)
    stmt = select(LeadTimeResult, VesselCall.vessel_name).join(
        VesselCall, VesselCall.id == LeadTimeResult.vessel_call_id
    ).where(
        LeadTimeResult.definition_id == definition_id,
        VesselCall.is_merged == False,
    )
    if target_tenant != "*":
        stmt = stmt.where(VesselCall.tenant_id == target_tenant)
    if result_status:
        stmt = stmt.where(LeadTimeResult.status == result_status)

    total_count = len(db.execute(stmt).all())
    rows = db.execute(stmt.order_by(LeadTimeResult.vcn.asc()).offset(skip).limit(limit)).all()

    items = []
    for r, v_name in rows:
        items.append({
            "id": str(r.id),
            "vessel_call_id": str(r.vessel_call_id),
            "vcn": r.vcn,
            "vessel_name": v_name,
            "duration_hours": r.duration_hours,
            "status": r.status,
            "unavailable_reason": r.unavailable_reason,
            "start_time": r.start_time.isoformat() if r.start_time else None,
            "end_time": r.end_time.isoformat() if r.end_time else None,
            # Traceability envelope (spec §2 & §10)
            "traceability": {
                "formula_version": r.formula_version,
                "source_record_ids": r.source_record_ids or [],
                "filter_context": r.filter_context or {},
                "exclusions_applied": r.exclusions_applied or [],
                "dq_status": r.dq_status,
                "calculated_at": r.calculated_at.isoformat() if r.calculated_at else None,
            },
        })

    return {
        "definition": {
            "id": str(defn.id),
            "name": defn.name,
            "formula_version": defn.formula_version,
            "unit": defn.unit,
        },
        "total": total_count,
        "skip": skip,
        "limit": limit,
        "items": items,
    }


@router.get("/metrics/{definition_id}/stats")
def get_metric_statistics(
    definition_id: str,
    cohort_key: str = Query("all"),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "vessel_call")),
):
    """Returns statistical aggregate for a definition, computing it if not yet present."""
    defn = db.execute(
        select(LeadTimeDefinition).where(LeadTimeDefinition.id == definition_id)
    ).scalar_one_or_none()
    if not defn:
        raise HTTPException(status_code=404, detail="LeadTimeDefinition not found")

    agg = db.execute(
        select(StatisticalAggregate).where(
            StatisticalAggregate.definition_id == definition_id,
            StatisticalAggregate.cohort_key == cohort_key,
        )
    ).scalar_one_or_none()

    if not agg:
        target_tenant = _resolve_target_tenant(principal)
        engine = AnalyticsEngine(db, tenant_id=target_tenant)
        agg = engine.compute_statistics(definition_id, cohort_key=cohort_key)
        db.commit()

    return {
        "definition_id": str(defn.id),
        "definition_name": defn.name,
        "cohort_key": agg.cohort_key,
        "observation_count": agg.observation_count,
        "missing_count": agg.missing_count,
        "mean_hours": agg.mean_hours,
        "median_hours": agg.median_hours,
        "std_hours": agg.std_hours,
        "cv": agg.cv,
        "min_hours": agg.min_hours,
        "max_hours": agg.max_hours,
        "p25_hours": agg.p25_hours,
        "p75_hours": agg.p75_hours,
        "p90_hours": agg.p90_hours,
        "p95_hours": agg.p95_hours,
        "fastest_vcn": agg.fastest_vcn,
        "slowest_vcn": agg.slowest_vcn,
        "tail_risk_ratio": agg.tail_risk_ratio,
        "right_skew_flag": agg.right_skew_flag,
        "percentile_method": agg.percentile_method,
        "small_sample_warning": agg.small_sample_warning,
        "outlier_vcns": agg.outlier_vcns or [],
        "formula_version": agg.formula_version,
        "quarantine_excluded": agg.quarantine_excluded,
        "calculated_at": agg.calculated_at.isoformat() if agg.calculated_at else None,
    }


@router.post("/custom")
def run_custom_lead_time(
    req: CustomLeadTimeRequest,
    tenant_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "vessel_call")),
):
    """Executes a custom lead-time calculation between any two canonical events with Polars statistics."""
    target_tenant = _resolve_target_tenant(principal, tenant_id)
    builder = CustomLeadTimeBuilder(db, tenant_id=target_tenant)
    try:
        res = builder.build(
            start_event=req.start_event,
            end_event=req.end_event,
            occurrence_selection=req.occurrence_selection,
            occurrence_n=req.occurrence_n,
            movement_scope=req.movement_scope,
            save_as_name=req.save_as_name,
            description=req.description,
            created_by_user=principal.email or principal.user_id,
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/vessel/{vessel_call_id}")
def get_vessel_call_lead_times(
    vessel_call_id: str,
    tenant_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "vessel_call")),
):
    """Returns all calculated lead-time metrics and stage contributions for a specific vessel call."""
    target_tenant = _resolve_target_tenant(principal, tenant_id)
    vc_stmt = select(VesselCall).where(VesselCall.id == vessel_call_id)
    if target_tenant != "*":
        vc_stmt = vc_stmt.where(VesselCall.tenant_id == target_tenant)
    vc = db.execute(vc_stmt).scalar_one_or_none()
    if not vc:
        raise HTTPException(status_code=404, detail="VesselCall not found")

    rows = db.execute(
        select(LeadTimeResult, LeadTimeDefinition)
        .join(LeadTimeDefinition, LeadTimeDefinition.id == LeadTimeResult.definition_id)
        .where(LeadTimeResult.vessel_call_id == vessel_call_id)
        .order_by(LeadTimeDefinition.name.asc())
    ).all()

    turnaround_hours = None
    for r, d in rows:
        if d.name == "Turnaround" and r.status == "AVAILABLE":
            turnaround_hours = r.duration_hours
            break

    metrics = []
    for r, d in rows:
        contribution = None
        if turnaround_hours and turnaround_hours > 0 and r.status == "AVAILABLE" and r.duration_hours is not None:
            contribution = round((r.duration_hours / turnaround_hours) * 100, 2)

        metrics.append({
            "metric_name": d.name,
            "definition_id": str(d.id),
            "status": r.status,
            "duration_hours": r.duration_hours,
            "contribution_pct_of_turnaround": contribution,
            "unavailable_reason": r.unavailable_reason,
            "start_time": r.start_time.isoformat() if r.start_time else None,
            "end_time": r.end_time.isoformat() if r.end_time else None,
            "dq_status": r.dq_status,
            "formula_version": r.formula_version,
        })

    return {
        "vessel_call_id": str(vc.id),
        "vcn": vc.vcn,
        "vessel_name": vc.vessel_name,
        "turnaround_hours": turnaround_hours,
        "metrics": metrics,
    }


@router.get("/reconciliation")
def get_reconciliation_scorecard(
    tolerance: float = Query(0.02, ge=0.001, le=1.0),
    tenant_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "vessel_call")),
):
    """Compares all 8 reconciliation target metrics against gold-standard testkit.expected_output."""
    target_tenant = _resolve_target_tenant(principal, tenant_id)
    engine = AnalyticsEngine(db, tenant_id=target_tenant)
    report = engine.reconcile_against_expected_outputs(tolerance=tolerance)
    return report
