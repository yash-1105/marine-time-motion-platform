"""REST API endpoints for outlier detection and transparent inclusion/exclusion (spec §10.6, Phase 09)."""
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.core.database import get_db
from apps.api.routers.auth import require
from apps.api.auth.principal import UserPrincipal
from apps.api.services.outliers.engine import OutlierEngine

router = APIRouter(prefix="/outliers", tags=["outliers"])


def _tenant(p: UserPrincipal) -> str:
    if p and p.data_scope and p.data_scope.tenant_id and p.data_scope.tenant_id != "*":
        return p.data_scope.tenant_id
    return "synthetic-tenant"


class ToggleExclusionRequest(BaseModel):
    is_excluded: bool
    rationale: str = Field(min_length=3, description="Governance justification for outlier exclusion/inclusion")


@router.get("", summary="List detected operational and data-quality outliers")
def list_outliers(
    outlier_type: Optional[str] = Query(None, description="OPERATIONAL_OUTLIER, DATA_QUALITY_OUTLIER, etc."),
    severity: Optional[str] = Query(None, description="MEDIUM, HIGH, CRITICAL"),
    is_excluded: Optional[bool] = Query(None, description="Filter by KPI exclusion status"),
    vcn: Optional[str] = Query(None, description="Filter by VCN"),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "analytics")),
):
    engine = OutlierEngine(db, tenant_id=_tenant(principal))
    return engine.list_outliers(
        outlier_type=outlier_type,
        severity=severity,
        is_excluded=is_excluded,
        vcn=vcn,
    )


@router.post("/detect", summary="Trigger outlier detection heuristics across canonical data")
def detect_outliers(
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("manage", "analytics")),
):
    engine = OutlierEngine(db, tenant_id=_tenant(principal))
    return engine.detect_all_outliers(persist=True)


@router.put("/{outlier_id}/exclusion", summary="Toggle outlier exclusion from KPI aggregates")
def toggle_outlier_exclusion(
    outlier_id: uuid.UUID,
    payload: ToggleExclusionRequest,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("manage", "analytics")),
):
    engine = OutlierEngine(db, tenant_id=_tenant(principal))
    try:
        return engine.toggle_outlier_exclusion(
            outlier_id=outlier_id,
            is_excluded=payload.is_excluded,
            rationale=payload.rationale,
            actor=principal.email or "data_steward",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
