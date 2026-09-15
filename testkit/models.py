"""ORM declarations for validation-only testkit schema tables."""

from sqlalchemy import Column, DateTime, Float, String
from sqlalchemy.dialects.postgresql import JSONB

from apps.api.models.base import BaseModel


class ExpectedOutput(BaseModel):
    __tablename__ = "expected_output"
    __table_args__ = {"schema": "testkit"}
    vcn = Column(String, nullable=False)
    metric_name = Column(String, nullable=False)
    expected_value = Column(Float, nullable=True)


class DQCase(BaseModel):
    __tablename__ = "dq_case"
    __table_args__ = {"schema": "testkit"}
    case_id = Column(String, nullable=False)
    description = Column(String, nullable=True)
    expected_outcome = Column(String, nullable=False)


class ValidationSummary(BaseModel):
    __tablename__ = "validation_summary"
    __table_args__ = {"schema": "testkit"}
    metric_name = Column(String, nullable=False)
    expected_value = Column(String, nullable=False)
    interpretation = Column(String, nullable=True)


class ValidationRunHistory(BaseModel):
    __tablename__ = "validation_run_history"
    __table_args__ = {"schema": "testkit"}
    run_timestamp = Column(DateTime(timezone=True), nullable=False)
    execution_time_seconds = Column(Float, nullable=False)
    app_version = Column(String, nullable=False)
    rule_version = Column(String, nullable=False)
    formula_version = Column(String, nullable=False)
    dataset_checksum = Column(String, nullable=False)
    overall_status = Column(String, nullable=False)
    report_json = Column(JSONB, nullable=False)
