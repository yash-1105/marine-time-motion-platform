"""REST API endpoints for delay analysis and cause allocation (spec §10.4, Phase 09)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.auth.principal import UserPrincipal
from apps.api.core.database import get_db
from apps.api.routers.auth import require
from apps.api.services.delays.inference import DelayInferenceEngine
from apps.api.services.delays.service import DelayService

router = APIRouter(prefix="/delays", tags=["delays"])


def _tenant(p: UserPrincipal) -> str:
    if p and p.data_scope and p.data_scope.tenant_id and p.data_scope.tenant_id != "*":
        return p.data_scope.tenant_id
    return "synthetic-tenant"


class CauseAllocationItem(BaseModel):
    canonical_category: str | None = None
    reason: str
    duration_hours: float
    is_primary: bool = False
    cause_status: str = "CONFIRMED"
    confidence: float | None = 1.0


class AllocateCausesRequest(BaseModel):
    allocations: list[CauseAllocationItem]
    rationale: str = Field(default="Analyst root cause breakdown")


class ReviewDelayReasonRequest(BaseModel):
    canonical_category: str
    reason: str
    decision: str = Field(default="APPROVED", pattern="^(APPROVED|REJECTED|UNDER_REVIEW)$")
    notes: str | None = None


@router.get("", summary="List delays with filters, search, and pagination")
def list_delays(
    stage: str | None = Query(None, description="Movement stage filter (Arrival, Sailing, Shifting)"),
    category: str | None = Query(None, description="Canonical category filter"),
    cause_status: str | None = Query(None, description="Confirmed vs Inferred"),
    resolution_status: str | None = Query(None, description="Open, Closed, Under Review"),
    search: str | None = Query(None, description="Search across VCN, vessel, reason"),
    has_mismatch: bool | None = Query(None, description="Filter reconciliation mismatches"),
    requires_review: bool | None = Query(None, description="Filter delays requiring reason review (DQ-007)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    sort_by: str = Query("total_duration_hours"),
    sort_order: str = Query("desc"),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "delays")),
):
    service = DelayService(db, tenant_id=_tenant(principal))
    return service.list_delays(
        movement_stage=stage,
        canonical_category=category,
        cause_status=cause_status,
        resolution_status=resolution_status,
        search=search,
        has_mismatch=has_mismatch,
        requires_review=requires_review,
        skip=skip,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/summary", summary="Get Pareto distribution and delay summary")
def get_delays_summary(
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "delays")),
):
    service = DelayService(db, tenant_id=_tenant(principal))
    return service.get_delays_summary()


@router.get("/{delay_id}", summary="Get delay detail with allocations and reconciliation")
def get_delay_detail(
    delay_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "delays")),
):
    service = DelayService(db, tenant_id=_tenant(principal))
    detail = service.get_delay_detail(delay_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Delay {delay_id} not found")
    return detail


@router.post("/{delay_id}/allocations", summary="Set multiple cause allocations for delay")
def allocate_causes(
    delay_id: uuid.UUID,
    payload: AllocateCausesRequest,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("edit", "delays")),
):
    service = DelayService(db, tenant_id=_tenant(principal))
    try:
        return service.allocate_causes(
            delay_id=delay_id,
            allocations_data=[a.model_dump() for a in payload.allocations],
            actor=principal.email or "lead_analyst",
            rationale=payload.rationale,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{delay_id}/infer", summary="Infer probable cause from operational evidence")
def infer_delay_cause(
    delay_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("edit", "delays")),
):
    engine = DelayInferenceEngine(db, tenant_id=_tenant(principal))
    try:
        return engine.infer_delay_cause(
            delay_id=delay_id,
            actor=principal.email or "ai_assistant",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{delay_id}/review", summary="Review and approve delay reason (e.g. DQ-007)")
def review_delay_reason(
    delay_id: uuid.UUID,
    payload: ReviewDelayReasonRequest,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("edit", "delays")),
):
    service = DelayService(db, tenant_id=_tenant(principal))
    try:
        return service.review_delay_reason(
            delay_id=delay_id,
            canonical_category=payload.canonical_category,
            reason=payload.reason,
            actor=principal.email or "lead_analyst",
            decision=payload.decision,
            notes=payload.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
