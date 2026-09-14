from typing import Any

from sqlalchemy.orm import Session

from apps.api.models.audit import AuditEvent


def log_audit_event(
    db: Session,
    action: str,
    actor_id: str | None = None,
    actor_email: str | None = None,
    actor_role: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    correlation_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    details: dict[str, Any] | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    filter_set: dict[str, Any] | None = None,
    row_count: int | None = None,
) -> AuditEvent:
    """Logs an auditable event to the append-only audit.audit_event table.

    Captures actor, role, action, resource, correlation ID, IP, user-agent,
    and structured details (including filter sets and row counts for exports).
    """
    merged_details: dict[str, Any] = details.copy() if details else {}
    if before is not None:
        merged_details["before"] = before
    if after is not None:
        merged_details["after"] = after
    if filter_set is not None:
        merged_details["filter_set"] = filter_set
    if row_count is not None:
        merged_details["row_count"] = row_count

    event = AuditEvent(
        actor_id=actor_id,
        actor_email=actor_email,
        actor_role=actor_role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        correlation_id=correlation_id,
        ip_address=ip_address,
        user_agent=user_agent,
        details=merged_details,
        # Backwards compatibility fields
        entity_name=resource_type or "system",
        entity_id=resource_id or "none",
        changes=merged_details,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
