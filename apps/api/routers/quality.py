from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from apps.api.dependencies import get_db
from apps.api.models.quality import QualityIssue
from apps.api.services.quality.engine import DataQualityEngine
from pydantic import BaseModel
from typing import List

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

class ResolveRequest(BaseModel):
    resolution_status: str
    notes: str

@router.post("/issues/{issue_id}/resolve")
def resolve_issue(issue_id: str, req: ResolveRequest, db: Session = Depends(get_db)):
    issue = db.execute(select(QualityIssue).where(QualityIssue.id == issue_id)).scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    issue.issue_status = req.resolution_status
    # Would store notes in resolution decision
    db.commit()
    return {"status": "success"}
