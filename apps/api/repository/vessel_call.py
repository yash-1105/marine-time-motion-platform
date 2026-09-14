import builtins
from typing import Any

from sqlalchemy.orm import Session

from apps.api.auth.scope import DataScope, ScopedQueryBuilder
from apps.api.models.canonical import VesselCall


class VesselCallRepository:
    """Repository enforcing DataScope boundary checks for vessel calls."""

    def __init__(self, db: Session):
        self.db = db

    def list(
        self,
        scope: DataScope,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        port_id: str | None = None,
        terminal_id: str | None = None,
        vessel_type: str | None = None,
        cargo_type: str | None = None,
        is_merged: bool | None = None,
        sort_by: str | None = "vcn",
        sort_dir: str | None = "asc",
    ) -> list[VesselCall]:
        from sqlalchemy import asc, desc, or_

        builder = ScopedQueryBuilder(VesselCall, scope)
        if search:
            s = f"%{search.strip()}%"
            builder.filter(
                or_(
                    VesselCall.vcn.ilike(s),
                    VesselCall.vessel_name.ilike(s),
                    VesselCall.imo_number.ilike(s),
                )
            )
        if port_id and port_id != "*":
            builder.filter(VesselCall.port_id == port_id)
        if terminal_id and terminal_id != "*":
            builder.filter(VesselCall.terminal_id == terminal_id)
        if vessel_type:
            builder.filter(VesselCall.vessel_type == vessel_type)
        if cargo_type:
            builder.filter(VesselCall.cargo_type == cargo_type)
        if is_merged is not None:
            builder.filter(VesselCall.is_merged == is_merged)

        query = builder.build(self.db)
        sort_col = getattr(VesselCall, sort_by or "vcn", VesselCall.vcn)
        if (sort_dir or "asc").lower() == "desc":
            query = query.order_by(desc(sort_col))
        else:
            query = query.order_by(asc(sort_col))

        return query.offset(skip).limit(limit).all()

    def count(
        self,
        scope: DataScope,
        search: str | None = None,
        port_id: str | None = None,
        terminal_id: str | None = None,
        vessel_type: str | None = None,
        cargo_type: str | None = None,
        is_merged: bool | None = None,
    ) -> int:
        from sqlalchemy import or_

        builder = ScopedQueryBuilder(VesselCall, scope)
        if search:
            s = f"%{search.strip()}%"
            builder.filter(
                or_(
                    VesselCall.vcn.ilike(s),
                    VesselCall.vessel_name.ilike(s),
                    VesselCall.imo_number.ilike(s),
                )
            )
        if port_id and port_id != "*":
            builder.filter(VesselCall.port_id == port_id)
        if terminal_id and terminal_id != "*":
            builder.filter(VesselCall.terminal_id == terminal_id)
        if vessel_type:
            builder.filter(VesselCall.vessel_type == vessel_type)
        if cargo_type:
            builder.filter(VesselCall.cargo_type == cargo_type)
        if is_merged is not None:
            builder.filter(VesselCall.is_merged == is_merged)

        query = builder.build(self.db)
        return query.count()

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
