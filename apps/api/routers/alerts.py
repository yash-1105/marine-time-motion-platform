"""REST API endpoints for operational alerts and remediation actions (spec §15, Phase 09)."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from apps.api.auth.principal import UserPrincipal
from apps.api.core.database import get_db
from apps.api.routers.auth import require
from apps.api.services.alerts.engine import AlertEngine

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _tenant(p: UserPrincipal) -> str:
    if p and p.data_scope and p.data_scope.tenant_id and p.data_scope.tenant_id != "*":
        return p.data_scope.tenant_id
    return "synthetic-tenant"


class AcknowledgeAlertRequest(BaseModel):
    pass


class ResolveAlertRequest(BaseModel):
    resolution_notes: str = Field(min_length=3, description="Resolution rationale or mitigation steps taken")


class CreateActionItemRequest(BaseModel):
    title: str = Field(min_length=3)
    description: str
    assigned_to: str | None = None
    due_date: datetime | None = None
    priority: str = Field(default="MEDIUM", pattern="^(LOW|MEDIUM|HIGH|URGENT)$")
    alert_id: uuid.UUID | None = None
    vessel_call_id: uuid.UUID | None = None


class UpdateActionItemRequest(BaseModel):
    status: str | None = Field(None, pattern="^(OPEN|IN_PROGRESS|COMPLETED|CANCELLED)$")
    comment: str | None = None


@router.get("", summary="List operational alerts")
def list_alerts(
    status: str | None = Query(None, description="NEW, ACKNOWLEDGED, RESOLVED"),
    severity: str | None = Query(None, description="LOW, MEDIUM, HIGH, CRITICAL"),
    rule_code: str | None = Query(None),
    vcn: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "operations")),
):
    engine = AlertEngine(db, tenant_id=_tenant(principal))
    return engine.list_alerts(status=status, severity=severity, rule_code=rule_code, vcn=vcn, limit=limit)


@router.post("/evaluate", summary="Evaluate operational alert rules")
def evaluate_alerts(
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("manage", "operations")),
):
    engine = AlertEngine(db, tenant_id=_tenant(principal))
    return engine.evaluate_rules()


@router.put("/{alert_id}/acknowledge", summary="Acknowledge an operational alert")
def acknowledge_alert(
    alert_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("manage", "operations")),
):
    engine = AlertEngine(db, tenant_id=_tenant(principal))
    try:
        return engine.acknowledge_alert(alert_id=alert_id, actor=principal.email or "operator")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{alert_id}/resolve", summary="Resolve an operational alert with resolution notes")
def resolve_alert(
    alert_id: uuid.UUID,
    payload: ResolveAlertRequest,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("manage", "operations")),
):
    engine = AlertEngine(db, tenant_id=_tenant(principal))
    try:
        return engine.resolve_alert(
            alert_id=alert_id,
            resolution_notes=payload.resolution_notes,
            actor=principal.email or "operator",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/actions", summary="List remediation action items")
def list_action_items(
    status: str | None = Query(None, description="OPEN, IN_PROGRESS, COMPLETED"),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "operations")),
):
    engine = AlertEngine(db, tenant_id=_tenant(principal))
    return engine.list_action_items(status=status)


@router.post("/actions", summary="Create a remediation action item")
def create_action_item(
    payload: CreateActionItemRequest,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("manage", "operations")),
):
    engine = AlertEngine(db, tenant_id=_tenant(principal))
    return engine.create_action_item(
        title=payload.title,
        description=payload.description,
        assigned_to=payload.assigned_to,
        due_date=payload.due_date,
        priority=payload.priority,
        alert_id=payload.alert_id,
        vessel_call_id=payload.vessel_call_id,
        created_by=principal.email or "operator",
    )


@router.put("/actions/{action_id}", summary="Update action item status or add comment")
def update_action_item(
    action_id: uuid.UUID,
    payload: UpdateActionItemRequest,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("manage", "operations")),
):
    engine = AlertEngine(db, tenant_id=_tenant(principal))
    try:
        return engine.update_action_item(
            action_id=action_id,
            status=payload.status,
            comment=payload.comment,
            actor=principal.email or "operator",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
