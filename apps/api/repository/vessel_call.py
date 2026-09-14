import builtins
from typing import Any

from sqlalchemy.orm import Session

from apps.api.auth.scope import DataScope, ScopedQueryBuilder
from apps.api.models.canonical import VesselCall


class VesselCallRepository:
    """Repository enforcing DataScope boundary checks for vessel calls."""

    def __init__(self, db: Session):
        self.db = db

    def list(self, scope: DataScope, skip: int = 0, limit: int = 100) -> list[VesselCall]:
        builder = ScopedQueryBuilder(VesselCall, scope)
        query = builder.build(self.db)
        return query.offset(skip).limit(limit).all()

    def get_by_id(self, scope: DataScope, call_id: str) -> VesselCall | None:
        builder = ScopedQueryBuilder(VesselCall, scope)
        query = builder.filter(VesselCall.id == call_id).build(self.db)
        return query.first()

    def create(self, scope: DataScope, **attributes) -> VesselCall:
        # Enforce tenant assignment from scope
        tenant_id = scope.tenant_id if scope.tenant_id != "*" else "default-tenant"
        port_id = attributes.get("port_id") or (scope.port_id if scope.port_id != "*" else "ZADUR")
        terminal_id = attributes.get("terminal_id") or (scope.terminal_id if scope.terminal_id != "*" else "DCT")

        call = VesselCall(
            tenant_id=tenant_id,
            port_id=port_id,
            terminal_id=terminal_id,
            **attributes,
        )
        self.db.add(call)
        self.db.commit()
        self.db.refresh(call)
        return call

    def export(self, scope: DataScope, filters: dict[str, Any] | None = None) -> builtins.list[VesselCall]:
        builder = ScopedQueryBuilder(VesselCall, scope)
        if filters:
            if "vessel_type" in filters:
                builder.filter(VesselCall.vessel_type == filters["vessel_type"])
        query = builder.build(self.db)
        return query.all()
