from sqlalchemy import Column, String, Boolean, ForeignKey, JSON, DateTime
from sqlalchemy.orm import relationship
from .base import BaseModel

class QualityRule(BaseModel):
    __tablename__ = 'quality_rule'
    __table_args__ = {'schema': 'quality'}
    rule_id = Column(String, nullable=False, unique=True)
    scope = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    pass_fail_expression = Column(String, nullable=False)
    remediation_guidance = Column(String, nullable=True)
    effective_from = Column(DateTime(timezone=True), nullable=True)
    effective_to = Column(DateTime(timezone=True), nullable=True)

class QualityIssue(BaseModel):
    __tablename__ = 'quality_issue'
    __table_args__ = {'schema': 'quality'}
    rule_id = Column(ForeignKey('quality.quality_rule.id'), nullable=False)
    vessel_call_id = Column(ForeignKey('canonical.vessel_call.id'), nullable=True)
    record_reference = Column(String, nullable=False)
    issue_status = Column(String, nullable=False) # OPEN|RESOLVED|QUARANTINED

class ResolutionDecision(BaseModel):
    __tablename__ = 'resolution_decision'
    __table_args__ = {'schema': 'quality'}
    quality_issue_id = Column(ForeignKey('quality.quality_issue.id'), nullable=False)
    decision = Column(String, nullable=False)
    notes = Column(String, nullable=True)
