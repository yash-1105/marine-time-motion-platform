from fastapi import HTTPException, status

from apps.api.auth.principal import UserPrincipal
from apps.api.core.config import settings


def resolve_principal_tenant(
    principal: UserPrincipal,
    requested_tenant: str | None = None,
) -> str:
    """Return the server-authenticated tenant without aliases or client overrides.

    Synthetic local principals with wildcard scope are bound to the configured
    development tenant. Outside that narrow case, a wildcard is insufficient for
    tenant-scoped persistence or reads because it is not a concrete identity.
    """
    tenant_id = (principal.data_scope.tenant_id or "").strip()
    if tenant_id == "*" and settings.environment == "development" and principal.is_synthetic:
        tenant_id = settings.development_tenant_id
    if not tenant_id or tenant_id == "*":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A concrete authenticated tenant scope is required",
        )
    if requested_tenant is not None and requested_tenant != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The requested tenant does not match the authenticated tenant scope",
        )
    return tenant_id
