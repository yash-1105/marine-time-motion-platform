from sqlalchemy import JSON, Column, String

from .base import BaseModel


class AuditEvent(BaseModel):
    __tablename__ = "audit_event"
    __table_args__ = {"schema": "audit"}

    # Actor information
    actor_id = Column(String, nullable=True)
    actor_email = Column(String, nullable=True)
    actor_role = Column(String, nullable=True)

    # Action & Resource
    action = Column(String, nullable=False)
    resource_type = Column(String, nullable=True)
    resource_id = Column(String, nullable=True)

    # Lineage / Context
    correlation_id = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)

    # Details (before/after, export filters, row counts, changes)
    details = Column(JSON, nullable=True)

    # Retained for backwards compatibility with Phase 01 seed / tests
    entity_name = Column(String, nullable=True)
    entity_id = Column(String, nullable=True)
    changes = Column(JSON, nullable=True)
