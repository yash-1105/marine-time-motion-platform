from sqlalchemy import Column, String, Float, Boolean, JSON
from .base import BaseModel

class ExpectedOutput(BaseModel):
    __tablename__ = 'expected_output'
    __table_args__ = {'schema': 'testkit'}
    vcn = Column(String, nullable=False)
    metric_name = Column(String, nullable=False)
    expected_value = Column(Float, nullable=True)

class DQCase(BaseModel):
    __tablename__ = 'dq_case'
    __table_args__ = {'schema': 'testkit'}
    case_id = Column(String, nullable=False)
    description = Column(String, nullable=True)
    expected_outcome = Column(String, nullable=False)
