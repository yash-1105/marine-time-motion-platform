
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import require
from apps.api.core.database import get_db
from apps.api.models.analytics import OutlierRecord
from apps.api.models.canonical import Delay, EventOccurrence, ServiceAssignment, ServiceExecution, ServiceRequest, VesselCall
from apps.api.models.ingestion import IngestionBatch, IngestionFile, StagingRecord
from apps.api.models.quality import QualityIssue, QualityRule
from apps.api.services.audit import log_audit_event
from apps.api.services.ingestion.pipeline import IngestionPipeline
from apps.api.services.ingestion.synthetic import reset_tenant_dataset
from apps.api.services.pipeline_runner import run_full_analytics_pipeline
from apps.api.services.quality.engine import DataQualityEngine

router = APIRouter(prefix="/quality", tags=["Quality"])

class QualityIssueSchema(BaseModel):
    id: str
    rule_id: str
    vessel_call_id: str | None = None
    record_reference: str
    issue_status: str
    rule_name: str | None = None
    severity: str | None = None
    scope: str | None = None
    remediation_guidance: str | None = None
    vcn: str | None = None
    vessel_name: str | None = None
    disposition: str | None = None
    workflow_state: str | None = None
    created_at: str | None = None
    issue_class: str = "QUALITY"
    source_file: str | None = None
    source_sheet: str | None = None
    source_row: int | None = None
    source_field: str | None = None
    original_values: dict | None = None
    reason: str | None = None
    movement_scope: str | None = None
    service_type: str | None = None
    is_excluded: bool = False


@router.post("/run")
def run_quality_engine(db: Session = Depends(get_db)):
    engine = DataQualityEngine(db)
    engine.run_all()
    return {"status": "success", "message": "Quality engine executed successfully"}


def _tenant(principal) -> str:
    return "synthetic-tenant" if principal.data_scope.tenant_id in ("*", "tenant-synthetic-01") else principal.data_scope.tenant_id


def _reference_object(db: Session, reference: str):
    """Resolve a DQ reference to its governed object without guessing values."""
    if ":" not in reference:
        return None
    kind, raw_id = reference.split(":", 1)
    model = {
        "StagingRecord": StagingRecord,
        "VesselCall": VesselCall,
        "EventOccurrence": EventOccurrence,
        "ServiceRequest": ServiceRequest,
        "ServiceAssignment": ServiceAssignment,
        "ServiceExecution": ServiceExecution,
        "Delay": Delay,
    }.get(kind)
    if not model:
        return None
    try:
        return db.execute(select(model).where(model.id == UUID(raw_id))).scalar_one_or_none()
    except (ValueError, TypeError):
        return None


def _source_context(db: Session, reference: str) -> dict:
    obj = _reference_object(db, reference)
    if obj is None:
        return {}
    if isinstance(obj, StagingRecord):
        row = obj
    else:
        lineage = getattr(obj, "source_lineage_id", None)
        if not lineage:
            return {"movement_scope": getattr(obj, "movement_scope", None) or getattr(obj, "movement_type", None)}
        try:
            file_id, sheet, row_number = lineage.rsplit(":", 2)
            row = db.execute(select(StagingRecord).where(
                StagingRecord.source_file_id == file_id,
                StagingRecord.worksheet_name == sheet,
                StagingRecord.row_number == int(row_number),
            )).scalar_one_or_none()
        except (ValueError, TypeError):
            row = None
    if row is None:
        return {}
    manifest = db.execute(select(IngestionFile).where(IngestionFile.id == row.source_file_id)).scalar_one_or_none()
    data = row.parsed_data or {}
    return {
        "staging_id": str(row.id),
        "source_file": manifest.original_filename if manifest else None,
        "source_sheet": row.worksheet_name,
        "source_row": row.row_number,
        "source_field": data.get("Event_Name") or data.get("Service_Type"),
        "original_values": data,
        "movement_scope": data.get("Movement_Type") or data.get("Movement") or getattr(obj, "movement_scope", None) or getattr(obj, "movement_type", None),
        "service_type": data.get("Service_Type"),
        "is_excluded": row.validation_status == "EXCLUDED",
    }


@router.get("/summary")
def get_quality_summary(db: Session = Depends(get_db)):
    """Returns aggregated data quality metrics for the operations center."""
    issues = db.execute(
        select(QualityIssue, QualityRule)
        .join(QualityRule, QualityIssue.rule_id == QualityRule.id)
    ).all()

    total_issues = len(issues)
    open_issues = sum(1 for iss, _ in issues if iss.issue_status != "RESOLVED")
    resolved_issues = sum(1 for iss, _ in issues if iss.issue_status == "RESOLVED")
    critical_issues = sum(1 for iss, r in issues if r.severity == "CRITICAL" and iss.issue_status != "RESOLVED")
    high_issues = sum(1 for iss, r in issues if r.severity == "HIGH" and iss.issue_status != "RESOLVED")

    # Quarantined calls
    quarantined_vcs = db.execute(
        select(QualityIssue.vessel_call_id)
        .join(QualityRule, QualityIssue.rule_id == QualityRule.id)
        .where(QualityRule.severity == "CRITICAL", QualityIssue.issue_status != "RESOLVED", QualityIssue.vessel_call_id.is_not(None))
        .distinct()
    ).scalars().all()

    total_vcs = db.execute(select(func.count(VesselCall.id)).where(VesselCall.is_merged == False)).scalar() or 1
    clean_vcs = max(0, total_vcs - len(quarantined_vcs))
    composite_cleanliness = round((clean_vcs / total_vcs) * 100, 1)

    # By severity
    by_severity = {
        "CRITICAL": sum(1 for _, r in issues if r.severity == "CRITICAL"),
        "HIGH": sum(1 for _, r in issues if r.severity == "HIGH"),
        "MEDIUM": sum(1 for _, r in issues if r.severity == "MEDIUM"),
        "LOW": sum(1 for _, r in issues if r.severity == "LOW"),
    }

    staging_counts = db.execute(
        select(StagingRecord.validation_status, func.count(StagingRecord.id)).group_by(StagingRecord.validation_status)
    ).all()
    staging_by_status = {status: count for status, count in staging_counts}
    outliers = db.execute(select(func.count(OutlierRecord.id))).scalar() or 0
    sequence_errors = sum(1 for iss, rule in issues if "SEQUENCE" in rule.rule_id or rule.rule_id in {"DQ-004", "DQ-006"})
    return {
        "total_issues": total_issues,
        "open_issues": open_issues,
        "resolved_issues": resolved_issues,
        "critical_issues": critical_issues,
        "high_issues": high_issues,
        "quarantined_calls_count": len(quarantined_vcs),
        "total_active_calls": total_vcs,
        "clean_calls_count": clean_vcs,
        "cleanliness_percentage": composite_cleanliness,
        "by_severity": by_severity,
        "total_rows": sum(staging_by_status.values()),
        "clean_rows": staging_by_status.get("VALID", 0),
        "incomplete_rows": sum(1 for iss, rule in issues if rule.scope in {"service_request", "service_assignment", "service_execution"} and "MISSING" in rule.rule_id),
        "sequence_errors": sequence_errors,
        "duplicate_rows": staging_by_status.get("DUPLICATE", 0),
        "outliers": outliers,
        "excluded_rows": staging_by_status.get("EXCLUDED", 0),
        "quarantined_rows": staging_by_status.get("QUARANTINED", 0),
    }


@router.get("/issues", response_model=list[QualityIssueSchema])
def list_issues(
    severity: str | None = None,
    issue_status: str | None = None,
    rule_id: str | None = None,
    search: str | None = None,
    vessel: str | None = None,
    file: str | None = None,
    service: str | None = None,
    movement_scope: str | None = None,
    outliers_only: bool = False,
    incomplete_only: bool = False,
    chronological_only: bool = False,
    db: Session = Depends(get_db),
):
    query = (
        select(QualityIssue, QualityRule, VesselCall)
        .join(QualityRule, QualityIssue.rule_id == QualityRule.id)
        .outerjoin(VesselCall, QualityIssue.vessel_call_id == VesselCall.id)
    )

    if severity:
        query = query.where(QualityRule.severity == severity.upper())
    if issue_status:
        query = query.where(QualityIssue.issue_status == issue_status.upper())
    if rule_id:
        query = query.where(QualityRule.rule_id == rule_id)
    if search:
        s = f"%{search.strip()}%"
        from sqlalchemy import or_
        query = query.where(
            or_(
                QualityRule.rule_id.ilike(s),
                QualityRule.pass_fail_expression.ilike(s),
                VesselCall.vcn.ilike(s),
                VesselCall.vessel_name.ilike(s),
                QualityIssue.record_reference.ilike(s),
            )
        )

    rows = db.execute(query).all()
    results = []
    for iss, rule, vc in rows:
        context = _source_context(db, iss.record_reference)
        if vessel and not ((vc and (vessel.lower() in (vc.vcn or "").lower() or vessel.lower() in (vc.vessel_name or "").lower()))):
            continue
        if file and file.lower() not in (context.get("source_file") or "").lower():
            continue
        if service and service.lower() not in (context.get("service_type") or "").lower():
            continue
        if movement_scope and movement_scope.upper() != "ALL" and (context.get("movement_scope") or "").upper() != movement_scope.upper():
            continue
        if outliers_only:
            continue  # governed outliers are exposed as a distinct issue class below
        if incomplete_only and "MISSING" not in rule.rule_id and rule.rule_id not in {"DQ-003", "DQ-005"}:
            continue
        if chronological_only and "SEQUENCE" not in rule.rule_id and rule.rule_id not in {"DQ-004", "DQ-006"}:
            continue
        results.append(
            QualityIssueSchema(
                id=str(iss.id),
                rule_id=rule.rule_id,
                vessel_call_id=str(iss.vessel_call_id) if iss.vessel_call_id else None,
                record_reference=iss.record_reference,
                issue_status=iss.issue_status,
                rule_name=rule.pass_fail_expression,
                severity=rule.severity,
                scope=rule.scope,
                remediation_guidance=rule.remediation_guidance,
                vcn=vc.vcn if vc else None,
                vessel_name=vc.vessel_name if vc else None,
                disposition="QUARANTINED" if rule.severity == "CRITICAL" and iss.issue_status != "RESOLVED" else "FLAGGED",
                workflow_state=iss.issue_status,
                created_at=iss.created_at.isoformat() if iss.created_at else None,
                reason=rule.pass_fail_expression,
                **context,
            )
        )
    # Outliers are not silently treated as bad source data.  They are separate,
    # inspectable analytical signals and are only included when requested.
    if outliers_only:
        outlier_query = select(OutlierRecord, VesselCall).join(VesselCall, OutlierRecord.vessel_call_id == VesselCall.id)
        for outlier, vc in db.execute(outlier_query).all():
            if vessel and vessel.lower() not in f"{vc.vcn or ''} {vc.vessel_name or ''}".lower():
                continue
            results.append(QualityIssueSchema(
                id=str(outlier.id), rule_id="OUTLIER", vessel_call_id=str(outlier.vessel_call_id),
                record_reference=f"OutlierRecord:{outlier.id}", issue_status="EXCLUDED" if outlier.is_excluded_from_kpi else "OPEN",
                rule_name=outlier.metric_name, severity=outlier.severity, scope="OUTLIER", vcn=vc.vcn,
                vessel_name=vc.vessel_name, disposition="EXCLUDED" if outlier.is_excluded_from_kpi else "REVIEW",
                workflow_state="EXCLUDED" if outlier.is_excluded_from_kpi else "OPEN", created_at=outlier.detected_at.isoformat() if outlier.detected_at else None,
                issue_class="OUTLIER", original_values=outlier.evidence, reason="Statistical outlier; review before excluding.",
                is_excluded=outlier.is_excluded_from_kpi,
            ))
    return results

@router.get("/score/{vessel_call_id}")
def get_quality_score(vessel_call_id: str, db: Session = Depends(get_db)):
    vc = db.execute(select(VesselCall).where(VesselCall.id == vessel_call_id)).scalar_one_or_none()
    if not vc:
        raise HTTPException(status_code=404, detail="Vessel call not found")
        
    issues = db.execute(
        select(QualityIssue, QualityRule)
        .join(QualityRule)
        .where(QualityIssue.vessel_call_id == vessel_call_id)
    ).all()
    
    components = {
        "COMPLETENESS": 100,
        "VALIDITY": 100,
        "CONSISTENCY": 100,
        "UNIQUENESS": 100,
        "TIMELINESS": 100,
        "LINEAGE": 100,
        "OPERATIONAL_SEQUENCE": 100,
        "IDENTITY": 100
    }
    
    for issue, rule in issues:
        if issue.issue_status != "CLOSED":
            # Deduct points based on severity
            penalty = {"CRITICAL": 50, "HIGH": 20, "MEDIUM": 10, "LOW": 5, "INFO": 0}.get(rule.severity, 10)
            rule_type = rule.type if hasattr(rule, 'type') and rule.type else "VALIDITY"
            if rule_type in components:
                components[rule_type] = max(0, components[rule_type] - penalty)
                
    composite = sum(components.values()) / len(components)
    
    return {
        "composite_score": composite,
        "components": components,
        "quarantined": vc.is_quarantined if hasattr(vc, "is_quarantined") else False
    }

class ResolveRequest(BaseModel):
    resolution_status: str
    notes: str

@router.post("/issues/{issue_id}/resolve")
def resolve_issue(issue_id: str, req: ResolveRequest, db: Session = Depends(get_db)):
    issue = db.execute(select(QualityIssue).where(QualityIssue.id == issue_id)).scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    issue.issue_status = req.resolution_status
    db.commit()
    return {"status": "success"}


class ExcludeIssuesRequest(BaseModel):
    issue_ids: list[UUID] = Field(min_length=1)
    reason: str = Field(min_length=3, max_length=2000)


@router.post("/exclusions", summary="Logically exclude selected source rows and rebuild governed analytics")
def exclude_issues_from_analysis(
    payload: ExcludeIssuesRequest,
    db: Session = Depends(get_db),
    principal=Depends(require("administer", "tenant")),
):
    tenant_id = _tenant(principal)
    active_batch = db.execute(select(IngestionBatch).where(
        IngestionBatch.tenant_id == tenant_id, IngestionBatch.is_active.is_(True), IngestionBatch.status == "COMMITTED"
    ).order_by(IngestionBatch.created_at.desc())).scalars().first()
    if not active_batch:
        raise HTTPException(status_code=404, detail="No active dataset is available for governed exclusion")
    issues = db.execute(select(QualityIssue).where(QualityIssue.id.in_(payload.issue_ids))).scalars().all()
    if len(issues) != len(set(payload.issue_ids)):
        raise HTTPException(status_code=404, detail="One or more quality issues were not found")
    rows: list[StagingRecord] = []
    for issue in issues:
        context = _source_context(db, issue.record_reference)
        staging_id = context.get("staging_id")
        if not staging_id:
            raise HTTPException(status_code=409, detail=f"{issue.record_reference} has no source staging lineage and cannot be excluded")
        row = db.execute(select(StagingRecord).where(StagingRecord.id == UUID(staging_id))).scalar_one()
        if row.ingestion_batch_id != active_batch.batch_id:
            raise HTTPException(status_code=409, detail="Only records from the active dataset may be excluded")
        rows.append(row)
    before = [{"staging_id": str(row.id), "status": row.validation_status, "errors": row.errors} for row in rows]
    for row in rows:
        row.validation_status = "EXCLUDED"
        errors = dict(row.errors or {})
        errors["analytical_exclusion"] = {"reason": payload.reason, "at": datetime.utcnow().isoformat() + "Z"}
        row.errors = errors
    db.flush()
    log_audit_event(
        db, action="EXCLUDE_FROM_ACTIVE_ANALYSIS", actor_id=principal.user_id, actor_email=principal.email,
        actor_role=",".join(principal.roles), resource_type="staging_record_group", resource_id=active_batch.batch_id,
        details={"reason": payload.reason, "issue_ids": [str(i.id) for i in issues], "source_records": [str(r.id) for r in rows]},
        before={"records": before}, after={"records": [{"staging_id": str(r.id), "status": r.validation_status} for r in rows]},
    )
    try:
        reset_tenant_dataset(db, tenant_id, keep_batches=True)
        pipeline = IngestionPipeline(db, tenant_id=tenant_id)
        pipeline._commit_to_canonical(active_batch)
        active_batch.is_active = True
        active_batch.status = "COMMITTED"
        db.commit()
        run_full_analytics_pipeline(db, tenant_id=tenant_id, batch_id=active_batch.batch_id, file_checksum=active_batch.file_checksum)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Exclusion was recorded but governed rebuild failed: {exc}")
    return {"status": "REBUILT", "batch_id": active_batch.batch_id, "excluded_rows": len(rows)}
