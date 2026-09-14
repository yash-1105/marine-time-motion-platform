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
    vessel_call_id: str
    record_reference: str
    issue_status: str

@router.post("/run")
def run_quality_engine(db: Session = Depends(get_db)):
    engine = DataQualityEngine(db)
    engine.run_all()
    return {"status": "success", "message": "Quality engine executed successfully"}

@router.get("/issues", response_model=List[QualityIssueSchema])
def list_issues(db: Session = Depends(get_db)):
    issues = db.execute(select(QualityIssue)).scalars().all()
    return [
        QualityIssueSchema(
            id=i.id,
            rule_id=i.rule_id,
            vessel_call_id=i.vessel_call_id,
            record_reference=i.record_reference,
            issue_status=i.issue_status
        ) for i in issues
    ]

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
