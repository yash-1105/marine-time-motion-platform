from sqlalchemy import Column, String, Float, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from .base import BaseModel

class MatchCandidate(BaseModel):
    __tablename__ = 'match_candidate'
    __table_args__ = {'schema': 'identity'}
    source_record_1_id = Column(String, nullable=False)
    source_record_2_id = Column(String, nullable=False)
    match_score = Column(Float, nullable=False)
    status = Column(String, nullable=False)

class MatchEvidence(BaseModel):
    __tablename__ = 'match_evidence'
    __table_args__ = {'schema': 'identity'}
    match_candidate_id = Column(ForeignKey('identity.match_candidate.id'), nullable=False)
    evidence_type = Column(String, nullable=False)
    evidence_detail = Column(JSON, nullable=False)

class MergeDecision(BaseModel):
    __tablename__ = 'merge_decision'
    __table_args__ = {'schema': 'identity'}
    match_candidate_id = Column(ForeignKey('identity.match_candidate.id'), nullable=False)
    decision = Column(String, nullable=False) # MERGED|REJECTED
    is_reversible = Column(Boolean, default=True)
