from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import require
from apps.api.auth.principal import UserPrincipal
from apps.api.auth.tenant import resolve_principal_tenant
from apps.api.core.database import get_db
from apps.api.models.reporting import ReportArtifact, ReportDelivery, ReportRun, ReportSchedule, ReportTemplate
from apps.api.services.audit import log_audit_event
from apps.api.services.reporting.service import ReportService, register_templates

router = APIRouter(prefix="/reports", tags=["reporting"])

def tenant(p: UserPrincipal) -> str: return resolve_principal_tenant(p)
class CreateReport(BaseModel):
    template_id: str = "daily-operations"; formats: list[str] = Field(default=["PDF", "XLSX", "PPTX", "DOCX"])
    period_start: datetime | None = None; period_end: datetime | None = None; filters: dict = Field(default_factory=dict)
class ScheduleRequest(BaseModel): template_id: str; frequency: str; formats: list[str]; recipients: list[str] = []; filters: dict = Field(default_factory=dict)
class DeliveryRequest(BaseModel): channel: str; recipient: str; simulate_failure: bool = False

@router.get("/templates")
def templates(db: Session = Depends(get_db), _: UserPrincipal = Depends(require("view", "reporting"))):
    register_templates(db); return [{"template_id": r.template_id, "version": r.template_version, "name": r.name, "status": r.status, "sections": r.section_definitions} for r in db.execute(select(ReportTemplate)).scalars()]

@router.get("/runs")
def runs(db: Session = Depends(get_db), principal: UserPrincipal = Depends(require("view", "reporting"))):
    """Returns report history constrained to the caller's authoritative scope."""
    stmt = select(ReportRun).where(ReportRun.tenant_id == tenant(principal)).order_by(ReportRun.created_at.desc()).limit(20)
    if principal.data_scope.port_id and principal.data_scope.port_id != "*": stmt = stmt.where(ReportRun.port_id == principal.data_scope.port_id)
    if principal.data_scope.terminal_id and principal.data_scope.terminal_id != "*": stmt = stmt.where(ReportRun.terminal_id == principal.data_scope.terminal_id)
    return [status(r) for r in db.execute(stmt).scalars().all()]

@router.post("")
def create(payload: CreateReport, db: Session = Depends(get_db), principal: UserPrincipal = Depends(require("create", "reporting"))):
    register_templates(db); t = db.execute(select(ReportTemplate).where(ReportTemplate.template_id == payload.template_id)).scalar_one_or_none()
    if not t: raise HTTPException(404, "Unknown report template")
    if t.status == "DEFERRED": raise HTTPException(409, "Template is registered but deferred; it cannot be generated.")
    formats = [x.upper() for x in payload.formats]
    if not formats or any(x not in {"PDF", "XLSX", "PPTX", "DOCX"} for x in formats): raise HTTPException(422, "Formats must be PDF, XLSX, PPTX, or DOCX")
    r = ReportRun(report_run_id=f"rpt-{uuid4().hex}", template_id=t.template_id, template_version=t.template_version, tenant_id=tenant(principal), port_id=principal.data_scope.port_id, terminal_id=principal.data_scope.terminal_id, period_start=payload.period_start, period_end=payload.period_end, filters=payload.filters, formats=formats, requested_by=principal.email)
    db.add(r); db.commit(); db.refresh(r); log_audit_event(db, "report_create", principal.user_id, principal.email, ",".join(principal.roles), "report_run", r.report_run_id, details={"formats": formats}); return status(r)

@router.post("/{run_id}/run")
def run_now(run_id: str, db: Session = Depends(get_db), principal: UserPrincipal = Depends(require("create", "reporting"))):
    r = find(db, run_id, principal); ReportService(db, r.tenant_id).generate(run_id); return status(r)
@router.get("/{run_id}")
def get(run_id: str, db: Session = Depends(get_db), principal: UserPrincipal = Depends(require("view", "reporting"))): return status(find(db, run_id, principal))
@router.get("/{run_id}/result")
def result(run_id: str, db: Session = Depends(get_db), principal: UserPrincipal = Depends(require("view", "reporting"))):
    run = find(db, run_id, principal)
    if not run.result_data: raise HTTPException(404, "Report result is not available yet")
    return {"report_run_id": run.report_run_id, "status": run.status, "result": run.result_data}
@router.post("/{run_id}/cancel")
def cancel(run_id: str, db: Session = Depends(get_db), principal: UserPrincipal = Depends(require("create", "reporting"))):
    r = find(db, run_id, principal); r.status, r.cancelled_at = "CANCELLED", datetime.now(UTC); db.commit(); return status(r)
@router.post("/{run_id}/retry")
def retry(run_id: str, db: Session = Depends(get_db), principal: UserPrincipal = Depends(require("create", "reporting"))):
    r = find(db, run_id, principal); r.status, r.failure_reason = "QUEUED", None; db.commit(); return status(r)
@router.post("/{run_id}/approve")
def approve(run_id: str, db: Session = Depends(get_db), principal: UserPrincipal = Depends(require("approve", "reporting"))):
    r = find(db, run_id, principal);
    if r.status != "AWAITING_APPROVAL": raise HTTPException(409, "Report is not awaiting approval")
    r.status, r.approved_by, r.approved_at = "APPROVED", principal.email, datetime.now(UTC); db.commit(); return status(r)
@router.post("/{run_id}/reject")
def reject(run_id: str, reason: str, db: Session = Depends(get_db), principal: UserPrincipal = Depends(require("reject", "reporting"))):
    r = find(db, run_id, principal); r.status, r.rejection_reason = "REJECTED", reason; db.commit(); return status(r)
@router.post("/{run_id}/publish")
def publish(run_id: str, db: Session = Depends(get_db), principal: UserPrincipal = Depends(require("publish", "reporting"))):
    r = find(db, run_id, principal);
    if r.status != "APPROVED": raise HTTPException(409, "Only approved reports may be published")
    r.status, r.published_at = "PUBLISHED", datetime.now(UTC); db.commit(); return status(r)
@router.get("/{run_id}/artifacts/{fmt}")
def artifact(run_id: str, fmt: str, db: Session = Depends(get_db), principal: UserPrincipal = Depends(require("view", "reporting"))):
    r = find(db, run_id, principal);
    if r.status != "PUBLISHED": raise HTTPException(403, "Artifact is not published")
    a = db.execute(select(ReportArtifact).where(ReportArtifact.report_run_id == r.id, ReportArtifact.format == fmt.upper())).scalar_one_or_none()
    if not a or not Path(a.storage_key).is_file(): raise HTTPException(404, "Artifact not found")
    return FileResponse(a.storage_key, media_type=a.content_type, filename=Path(a.storage_key).name)
@router.post("/{run_id}/deliver")
def deliver(run_id: str, payload: DeliveryRequest, db: Session = Depends(get_db), principal: UserPrincipal = Depends(require("publish", "reporting"))):
    r = find(db, run_id, principal);
    if r.status != "PUBLISHED": raise HTTPException(409, "Only published reports can be delivered")
    return delivery(ReportService(db, r.tenant_id).deliver(r, payload.channel, payload.recipient, payload.simulate_failure))
@router.post("/deliveries/{delivery_id}/retry")
def retry_delivery(delivery_id: str, db: Session = Depends(get_db), principal: UserPrincipal = Depends(require("publish", "reporting"))):
    d = db.get(ReportDelivery, delivery_id)
    if not d: raise HTTPException(404, "Delivery not found")
    r = db.get(ReportRun, d.report_run_id); find(db, r.report_run_id, principal); return delivery(ReportService(db, r.tenant_id).retry_delivery(d))
@router.post("/schedules")
def schedule(payload: ScheduleRequest, db: Session = Depends(get_db), principal: UserPrincipal = Depends(require("configure", "reporting"))):
    s = ReportSchedule(template_id=payload.template_id, tenant_id=tenant(principal), frequency=payload.frequency, formats=payload.formats, recipients=payload.recipients, filters=payload.filters); db.add(s); db.commit(); return {"id": str(s.id), "scheduler_notice": "A deployment scheduler must invoke this model; cron execution is intentionally not bundled."}

def find(db, run_id, principal):
    stmt = select(ReportRun).where(ReportRun.report_run_id == run_id, ReportRun.tenant_id == tenant(principal))
    if principal.data_scope.port_id and principal.data_scope.port_id != "*": stmt = stmt.where(ReportRun.port_id == principal.data_scope.port_id)
    if principal.data_scope.terminal_id and principal.data_scope.terminal_id != "*": stmt = stmt.where(ReportRun.terminal_id == principal.data_scope.terminal_id)
    r = db.execute(stmt).scalar_one_or_none()
    if not r: raise HTTPException(404, "Report run not found in data scope")
    return r
def status(r): return {"report_run_id": r.report_run_id, "status": r.status, "progress": r.progress, "template_id": r.template_id, "formats": r.formats, "failure_reason": r.failure_reason, "version": r.version}
def delivery(d): return {"id": str(d.id), "status": d.status, "attempts": d.attempts, "error_message": d.error_message}
