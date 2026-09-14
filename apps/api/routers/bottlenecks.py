"""REST API endpoints for operational bottleneck scoring (spec §10.5, Phase 09)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.auth.principal import UserPrincipal
from apps.api.core.database import get_db
from apps.api.routers.auth import require
from apps.api.services.bottlenecks.engine import BottleneckEngine

router = APIRouter(prefix="/bottlenecks", tags=["bottlenecks"])


def _tenant(p: UserPrincipal) -> str:
    if p and p.data_scope and p.data_scope.tenant_id and p.data_scope.tenant_id != "*":
        return p.data_scope.tenant_id
    return "synthetic-tenant"


class RecalculateBottlenecksRequest(BaseModel):
    weights: dict[str, float] | None = None


@router.get("", summary="Get ranked operational bottlenecks with component scores")
def get_bottlenecks(
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "analytics")),
):
    engine = BottleneckEngine(db, tenant_id=_tenant(principal))
    return engine.calculate_bottlenecks(persist=False)


@router.post("/recalculate", summary="Recalculate and persist bottleneck rankings")
def recalculate_bottlenecks(
    payload: RecalculateBottlenecksRequest | None = None,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("manage", "analytics")),
):
    engine = BottleneckEngine(db, tenant_id=_tenant(principal))
    weights = payload.weights if payload else None
    return engine.calculate_bottlenecks(weights=weights, persist=True)
