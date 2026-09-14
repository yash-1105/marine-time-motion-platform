from sqlalchemy import Column, String, JSON
from .base import BaseModel

class AuditEvent(BaseModel):
    __tablename__ = 'audit_event'
    __table_args__ = {'schema': 'audit'}
    entity_name = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    action = Column(String, nullable=False)
    changes = Column(JSON, nullable=False)
