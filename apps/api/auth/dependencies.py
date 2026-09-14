from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from apps.api.auth.principal import UserPrincipal
from apps.api.auth.scope import DataScope
from apps.api.core.database import get_db
from apps.api.core.security import decode_token
from apps.api.services.audit import log_audit_event
from apps.api.services.auth_service import is_session_active

security_scheme = HTTPBearer(auto_error=False)


def get_current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> UserPrincipal:
    """Extracts and validates the UserPrincipal from Bearer token or session cookie."""
    token: str | None = None

    if credentials and credentials.credentials:
        token = credentials.credentials
    elif "access_token" in request.cookies:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Missing authentication credentials",
                "correlation_id": getattr(request.state, "correlation_id", "unknown"),
            },
        )

    try:
        payload: dict[str, Any] = decode_token(token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_TOKEN",
                "message": str(e),
                "correlation_id": getattr(request.state, "correlation_id", "unknown"),
            },
        )

    jti = payload.get("jti")
    if jti and not is_session_active(db, jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "SESSION_EXPIRED",
                "message": "Session has been revoked or expired due to inactivity",
                "correlation_id": getattr(request.state, "correlation_id", "unknown"),
            },
        )

    scope_data = payload.get("data_scope", {})
    data_scope = DataScope(
        tenant_id=scope_data.get("tenant_id", "default-tenant"),
        port_id=scope_data.get("port_id"),
        terminal_id=scope_data.get("terminal_id"),
    )

    principal = UserPrincipal(
        user_id=payload.get("sub", ""),
        email=payload.get("email", ""),
        roles=payload.get("roles", []),
        permissions=payload.get("permissions", []),
        data_scope=data_scope,
        is_service_account=payload.get("is_service_account", False),
        is_synthetic=payload.get("is_synthetic", True),
        session_jti=jti,
    )

    request.state.principal = principal
    request.state.scope = data_scope
    return principal


class PermissionDependency:
    """Callable class representing a permission and resource authorization check."""

    def __init__(self, permission: str, resource: str | None = None):
        self.permission = permission
        self.resource = resource
        self.__is_permission_dependency__ = True

    def __call__(
        self,
        request: Request,
        principal: UserPrincipal = Depends(get_current_principal),
        db: Session = Depends(get_db),
    ) -> UserPrincipal:
        correlation_id = getattr(request.state, "correlation_id", "unknown")
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")

        # Action-based check
        if not principal.has_permission(self.permission):
            # Log failed authorization
            log_audit_event(
                db=db,
                action="failed_auth",
                actor_id=principal.user_id,
                actor_email=principal.email,
                actor_role=",".join(principal.roles),
                resource_type=self.resource or "endpoint",
                resource_id=request.url.path,
                correlation_id=correlation_id,
                ip_address=ip,
                user_agent=ua,
                details={
                    "required_permission": self.permission,
                    "principal_permissions": principal.permissions,
                    "reason": "Forbidden: missing required action permission",
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN",
                    "message": f"Action '{self.permission}' not permitted for role(s): {', '.join(principal.roles)}",
                    "required_permission": self.permission,
                    "correlation_id": correlation_id,
                },
            )

        return principal


def require(permission: str, resource: str | None = None) -> PermissionDependency:
    """FastAPI authorization dependency factory used by all protected routes."""
    return PermissionDependency(permission=permission, resource=resource)
