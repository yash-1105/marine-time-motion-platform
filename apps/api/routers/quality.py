from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from apps.api.core.database import get_db
from apps.api.models.quality import QualityIssue, QualityRule
from apps.api.models.canonical import VesselCall
from apps.api.services.quality.engine import DataQualityEngine
from pydantic import BaseModel
from typing import List, Dict

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


@router.post("/run")
def run_quality_engine(db: Session = Depends(get_db)):
    engine = DataQualityEngine(db)
    engine.run_all()
    return {"status": "success", "message": "Quality engine executed successfully"}


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
    }


@router.get("/issues", response_model=List[QualityIssueSchema])
def list_issues(
    severity: str | None = None,
    issue_status: str | None = None,
    rule_id: str | None = None,
    search: str | None = None,
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
            )
        )
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
