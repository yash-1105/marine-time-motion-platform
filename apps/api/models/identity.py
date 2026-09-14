from sqlalchemy import JSON, Boolean, Column, Float, ForeignKey, String
from sqlalchemy.orm import relationship

from .base import BaseModel


class MatchCandidate(BaseModel):
    __tablename__ = "match_candidate"
    __table_args__ = {"schema": "identity"}
    source_record_1_id = Column(String, nullable=False)
    source_record_2_id = Column(String, nullable=False)
    match_score = Column(Float, nullable=False)
    status = Column(String, nullable=False)  # AUTO_MERGE_CANDIDATE | STEWARD_REVIEW | SEPARATE | BLOCKED_BY_CONFLICT | MERGED
    match_type = Column(String, nullable=True)  # DETERMINISTIC | PROBABILISTIC
    conflict_detected = Column(Boolean, default=False, nullable=False)
    conflict_reasons = Column(JSON, nullable=True)

    evidences = relationship("MatchEvidence", back_populates="candidate", cascade="all, delete-orphan")
    decisions = relationship("MergeDecision", back_populates="candidate", cascade="all, delete-orphan")


class MatchEvidence(BaseModel):
    __tablename__ = "match_evidence"
    __table_args__ = {"schema": "identity"}
    match_candidate_id = Column(ForeignKey("identity.match_candidate.id"), nullable=False)
    evidence_type = Column(String, nullable=False)
    evidence_detail = Column(JSON, nullable=False)

    candidate = relationship("MatchCandidate", back_populates="evidences")


class MergeDecision(BaseModel):
    __tablename__ = "merge_decision"
    __table_args__ = {"schema": "identity"}
    match_candidate_id = Column(ForeignKey("identity.match_candidate.id"), nullable=False)
    decision = Column(String, nullable=False)  # MERGED | REJECTED | UNMERGED
    is_reversible = Column(Boolean, default=True)

    survivor_record_id = Column(String, nullable=True)
    merged_record_id = Column(String, nullable=True)
    evidence_snapshot = Column(JSON, nullable=True)
    prior_state_snapshot = Column(JSON, nullable=True)
    rule_version = Column(String, nullable=True)
    actor = Column(String, nullable=True)
    notes = Column(String, nullable=True)

    candidate = relationship("MatchCandidate", back_populates="decisions")
