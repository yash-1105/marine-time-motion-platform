from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import require
from apps.api.auth.principal import UserPrincipal
from apps.api.core.database import get_db
from apps.api.models.audit import AuditEvent

router = APIRouter(prefix="/audit", tags=["Audit and Lineage"])


@router.get("/events")
def list_audit_events(
    limit: int = Query(50, ge=1, le=200),
    action: str | None = None,
    principal: UserPrincipal = Depends(require("audit", "audit_trail")),
    db: Session = Depends(get_db),
):
    """Lists audit events. Strictly requires the 'audit' action permission."""
    query = db.query(AuditEvent)
    if action:
        query = query.filter(AuditEvent.action == action)
    events = query.order_by(AuditEvent.created_at.desc()).limit(limit).all()

    return [
        {
            "id": str(e.id),
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "action": e.action,
            "actor_id": e.actor_id,
            "actor_email": e.actor_email,
            "actor_role": e.actor_role,
            "resource_type": e.resource_type,
            "resource_id": e.resource_id,
            "correlation_id": e.correlation_id,
            "ip_address": e.ip_address,
            "user_agent": e.user_agent,
            "details": e.details,
        }
        for e in events
    ]
