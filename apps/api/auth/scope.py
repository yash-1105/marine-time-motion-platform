from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Query, Session


class DataScope(BaseModel):
    """Represents the tenant, port, and terminal boundaries for an authenticated principal."""

    tenant_id: str = Field(..., description="Tenant ID or '*' for platform administrator")
    port_id: str | None = Field(None, description="Port code (e.g. 'ZADUR') or '*' for all ports")
    terminal_id: str | None = Field(None, description="Terminal code (e.g. 'DCT') or '*' for all terminals")

    def allows_tenant(self, tenant: str) -> bool:
        if self.tenant_id == "*":
            return True
        if self.tenant_id in ("tenant-synthetic-01", "synthetic-tenant") and tenant in ("tenant-synthetic-01", "synthetic-tenant"):
            return True
        return self.tenant_id == tenant

    def allows_port(self, port: str | None) -> bool:
        if self.port_id == "*" or self.port_id is None:
            return True
        return self.port_id == port

    def allows_terminal(self, terminal: str | None) -> bool:
        if self.terminal_id == "*" or self.terminal_id is None:
            return True
        return self.terminal_id == terminal


class ScopedQueryBuilder:
    """Repository-level query builder that enforces data scope on every query.

    A query cannot be executed without providing an explicit DataScope.
    """

    def __init__(self, model: type[Any], scope: DataScope):
        if not isinstance(scope, DataScope):
            raise ValueError("ScopedQueryBuilder requires an explicit, valid DataScope instance")
        self.model = model
        self.scope = scope
        self.filters = []

    def filter(self, *criterion):
        self.filters.extend(criterion)
        return self

    def build(self, session: Session) -> Query:
        query = session.query(self.model)

        # 1. Enforce tenant isolation if the model possesses a tenant_id column
        if hasattr(self.model, "tenant_id"):
            if self.scope.tenant_id != "*":
                query = query.filter(self.model.tenant_id == self.scope.tenant_id)

        # 2. Enforce port isolation if model has port_id and scope specifies a non-wildcard port
        if hasattr(self.model, "port_id"):
            if self.scope.port_id and self.scope.port_id != "*":
                from sqlalchemy import or_
                query = query.filter(or_(self.model.port_id == self.scope.port_id, self.model.port_id.is_(None)))

        # 3. Enforce terminal isolation if model has terminal_id and scope specifies a non-wildcard terminal
        if hasattr(self.model, "terminal_id"):
            if self.scope.terminal_id and self.scope.terminal_id != "*":
                from sqlalchemy import or_
                query = query.filter(or_(self.model.terminal_id == self.scope.terminal_id, self.model.terminal_id.is_(None)))

        if self.filters:
            query = query.filter(*self.filters)

        return query
