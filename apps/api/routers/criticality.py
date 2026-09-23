"""REST API endpoints for operational criticality evaluation (spec §10.8, Phase 09)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.auth.principal import UserPrincipal
from apps.api.auth.tenant import resolve_principal_tenant
from apps.api.core.database import get_db
from apps.api.routers.auth import require
from apps.api.services.criticality.engine import CriticalityEngine

router = APIRouter(prefix="/criticality", tags=["criticality"])


def _tenant(p: UserPrincipal) -> str:
    return resolve_principal_tenant(p)


class EvaluateCriticalityRequest(BaseModel):
    duration_hours: float = Field(ge=0.0)
    cv: float = Field(ge=0.0)
    tail_risk_ratio: float = Field(ge=0.0)
    weights: dict[str, float] | None = None


@router.get("", summary="Get operational criticality evaluation across all stages")
def get_criticality_evaluations(
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "analytics")),
):
    engine = CriticalityEngine(db, tenant_id=_tenant(principal))
    return engine.evaluate_all_stages()


@router.post("/evaluate", summary="Calculate criticality component scores for custom parameters")
def evaluate_custom_criticality(
    payload: EvaluateCriticalityRequest,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "analytics")),
):
    engine = CriticalityEngine(db, tenant_id=_tenant(principal))
    return engine.compute_component_scores(
        duration_hours=payload.duration_hours,
        cv=payload.cv,
        tail_risk_ratio=payload.tail_risk_ratio,
        weights=payload.weights,
    )
