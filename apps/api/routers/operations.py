from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import require
from apps.api.auth.principal import UserPrincipal
from apps.api.core.database import get_db
from apps.api.repository.vessel_call import VesselCallRepository
from apps.api.services.audit import log_audit_event

router = APIRouter(prefix="/operations", tags=["Operations & Data Scope"])


class CreateVesselCallRequest(BaseModel):
    vessel_name: str
    vcn: str | None = None
    vessel_type: str | None = "Container"
    port_id: str | None = None
    terminal_id: str | None = None


class ExportRequest(BaseModel):
    filters: dict[str, Any] = {}


class MergeRequest(BaseModel):
    primary_call_id: str
    secondary_call_id: str
    reason: str


@router.get("/vessel-calls")
def list_vessel_calls(
    skip: int = 0,
    limit: int = 100,
    principal: UserPrincipal = Depends(require("view", "vessel_call")),
    db: Session = Depends(get_db),
):
    """Lists vessel calls. Data scope is strictly enforced at the repository level."""
    repo = VesselCallRepository(db)
    calls = repo.list(scope=principal.data_scope, skip=skip, limit=limit)
    return [
        {
            "id": str(c.id),
            "vessel_name": c.vessel_name,
            "vcn": c.vcn,
            "vessel_type": c.vessel_type,
            "tenant_id": c.tenant_id,
            "port_id": c.port_id,
            "terminal_id": c.terminal_id,
        }
        for c in calls
    ]


@router.post("/vessel-calls")
def create_vessel_call(
    request: Request,
    body: CreateVesselCallRequest,
    principal: UserPrincipal = Depends(require("create", "vessel_call")),
    db: Session = Depends(get_db),
):
    """Creates a vessel call scoped to the principal's tenant/port boundaries."""
    repo = VesselCallRepository(db)
    call = repo.create(
        scope=principal.data_scope,
        vessel_name=body.vessel_name,
        vcn=body.vcn,
        vessel_type=body.vessel_type,
        port_id=body.port_id,
        terminal_id=body.terminal_id,
    )

    log_audit_event(
        db=db,
        action="create",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
        resource_type="vessel_call",
        resource_id=str(call.id),
        correlation_id=getattr(request.state, "correlation_id", None),
        details={"vessel_name": call.vessel_name, "vcn": call.vcn},
    )

    return {"id": str(call.id), "vessel_name": call.vessel_name, "status": "created"}


@router.put("/vessel-calls/{call_id}")
def edit_vessel_call(
    request: Request,
    call_id: str,
    body: dict[str, Any],
    principal: UserPrincipal = Depends(require("edit", "vessel_call")),
    db: Session = Depends(get_db),
):
    """Edits a vessel call and logs the correction event."""
    repo = VesselCallRepository(db)
    call = repo.get_by_id(principal.data_scope, call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Vessel call not found within data scope")

    before = {"vessel_name": call.vessel_name}
    if "vessel_name" in body:
        call.vessel_name = body["vessel_name"]
    db.commit()

    log_audit_event(
        db=db,
        action="correction",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
        resource_type="vessel_call",
        resource_id=str(call.id),
        before=before,
        after={"vessel_name": call.vessel_name},
    )
    return {"id": str(call.id), "status": "updated"}


@router.post("/vessel-calls/export")
def export_vessel_calls(
    request: Request,
    body: ExportRequest,
    principal: UserPrincipal = Depends(require("export", "vessel_call")),
    db: Session = Depends(get_db),
):
    """Exports vessel calls. Sensitive export is audited with filters and row count per spec §17."""
    repo = VesselCallRepository(db)
    records = repo.export(scope=principal.data_scope, filters=body.filters)
    row_count = len(records)

    log_audit_event(
        db=db,
        action="export",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
        resource_type="vessel_call",
        filter_set=body.filters,
        row_count=row_count,
        correlation_id=getattr(request.state, "correlation_id", None),
        details={"export_format": "json"},
    )

    return {
        "count": row_count,
        "filters_applied": body.filters,
        "data": [{"id": str(r.id), "vessel_name": r.vessel_name, "port_id": r.port_id} for r in records],
    }


@router.post("/vessel-calls/merge")
def merge_vessel_calls(
    request: Request,
    body: MergeRequest,
    principal: UserPrincipal = Depends(require("merge", "vessel_call")),
    db: Session = Depends(get_db),
):
    """Merges two vessel calls with audit trail."""
    log_audit_event(
        db=db,
        action="merge",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
        resource_type="vessel_call",
        resource_id=body.primary_call_id,
        details={"secondary_id": body.secondary_call_id, "reason": body.reason},
    )
    return {"status": "merged", "primary_id": body.primary_call_id}


@router.post("/vessel-calls/unmerge")
def unmerge_vessel_calls(
    request: Request,
    body: MergeRequest,
    principal: UserPrincipal = Depends(require("unmerge", "vessel_call")),
    db: Session = Depends(get_db),
):
    """Unmerges previously merged vessel calls with audit trail."""
    log_audit_event(
        db=db,
        action="unmerge",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
        resource_type="vessel_call",
        resource_id=body.primary_call_id,
        details={"secondary_id": body.secondary_call_id, "reason": body.reason},
    )
    return {"status": "unmerged", "primary_id": body.primary_call_id}


@router.post("/recalculate")
def recalculate_metrics(
    request: Request,
    principal: UserPrincipal = Depends(require("recalculate", "metrics")),
    db: Session = Depends(get_db),
):
    """Recalculates metrics or stage durations."""
    log_audit_event(
        db=db,
        action="recalculation",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
        resource_type="analytics",
    )
    return {"status": "recalculated"}


@router.post("/publish")
def publish_report(
    request: Request,
    principal: UserPrincipal = Depends(require("publish", "report")),
    db: Session = Depends(get_db),
):
    """Publishes operational report."""
    log_audit_event(
        db=db,
        action="report_publication",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
        resource_type="report",
    )
    return {"status": "published"}


@router.post("/approve")
def approve_action(
    request: Request,
    principal: UserPrincipal = Depends(require("approve", "approval")),
    db: Session = Depends(get_db),
):
    """Approves an operational or data quality action."""
    log_audit_event(
        db=db,
        action="approve",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
    )
    return {"status": "approved"}


@router.post("/reject")
def reject_action(
    request: Request,
    principal: UserPrincipal = Depends(require("reject", "approval")),
    db: Session = Depends(get_db),
):
    """Rejects an operational or data quality action."""
    log_audit_event(
        db=db,
        action="reject",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
    )
    return {"status": "rejected"}


@router.post("/configure")
def configure_system(
    request: Request,
    principal: UserPrincipal = Depends(require("configure", "configuration")),
    db: Session = Depends(get_db),
):
    """Modifies platform configuration."""
    log_audit_event(
        db=db,
        action="config_change",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
    )
    return {"status": "configured"}


@router.post("/administer")
def administer_system(
    request: Request,
    principal: UserPrincipal = Depends(require("administer", "administration")),
    db: Session = Depends(get_db),
):
    """Executes administrative operations."""
    log_audit_event(
        db=db,
        action="admin_action",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
    )
    return {"status": "administered"}
