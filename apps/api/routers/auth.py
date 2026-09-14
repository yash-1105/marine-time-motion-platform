from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import require
from apps.api.auth.principal import UserPrincipal
from apps.api.core.database import get_db
from apps.api.services.audit import log_audit_event
from apps.api.services.auth_service import (
    authenticate_service_account,
    create_user_session,
    get_oidc_authorization_url,
    refresh_user_session,
    revoke_session,
)
from apps.api.services.dev_auth_provider import (
    authenticate_dev_user,
    get_dev_users,
    verify_dev_provider_allowed,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


class ServiceAccountLoginRequest(BaseModel):
    client_id: str
    client_secret: str


class DevLoginRequest(BaseModel):
    role_or_email: str


class RefreshRequest(BaseModel):
    refresh_token: str


@router.get("/login")
def login_redirect(state: str | None = "state_marine_platform"):
    """Returns OIDC authorization URL with PKCE (Microsoft Entra ID compatible)."""
    auth_url, code_verifier = get_oidc_authorization_url(state=state or "state")
    return {
        "authorization_url": auth_url,
        "code_verifier": code_verifier,
        "instructions": "Redirect user to authorization_url with PKCE code_challenge",
    }


@router.post("/service-token")
def service_account_token(
    request: Request,
    body: ServiceAccountLoginRequest,
    db: Session = Depends(get_db),
):
    """Exchanges scoped machine service account credentials for an access token."""
    session_data = authenticate_service_account(db=db, client_id=body.client_id, client_secret=body.client_secret)
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    if not session_data:
        log_audit_event(
            db=db,
            action="failed_auth",
            actor_email=body.client_id,
            resource_type="service_account",
            correlation_id=correlation_id,
            ip_address=ip,
            user_agent=ua,
            details={"reason": "Invalid service account client_id or secret"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Invalid service credentials"},
        )

    log_audit_event(
        db=db,
        action="login",
        actor_id=session_data.get("session_id"),
        actor_email=body.client_id,
        actor_role="Integration Service Account",
        resource_type="service_account",
        correlation_id=correlation_id,
        ip_address=ip,
        user_agent=ua,
        details={"type": "machine_token_issued"},
    )
    return session_data


@router.get("/dev/users")
def list_dev_users(db: Session = Depends(get_db)):
    """Lists seeded development users. Refused outside development."""
    try:
        verify_dev_provider_allowed()
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    return get_dev_users(db)


@router.post("/dev/login")
def dev_login(
    request: Request,
    body: DevLoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    """Fast login as any seeded role for local development. Refused outside development."""
    try:
        verify_dev_provider_allowed()
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    user_info = authenticate_dev_user(db, body.role_or_email)
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    if not user_info:
        log_audit_event(
            db=db,
            action="failed_auth",
            actor_email=body.role_or_email,
            correlation_id=correlation_id,
            ip_address=ip,
            user_agent=ua,
            details={"reason": "Unknown development user/role"},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": f"Seeded user for '{body.role_or_email}' not found"},
        )

    session_data = create_user_session(
        db=db,
        user_id=user_info["user_id"],
        email=user_info["email"],
        roles=user_info["roles"],
        permissions=user_info["permissions"],
        data_scope=user_info["data_scope"],
        is_service_account=False,
    )

    # Set secure HttpOnly cookie for web client
    response.set_cookie(
        key="access_token",
        value=session_data["access_token"],
        httponly=True,
        samesite="lax",
        secure=False,
    )

    log_audit_event(
        db=db,
        action="login",
        actor_id=user_info["user_id"],
        actor_email=user_info["email"],
        actor_role=",".join(user_info["roles"]),
        correlation_id=correlation_id,
        ip_address=ip,
        user_agent=ua,
        details={"login_method": "development_provider"},
    )

    return session_data


@router.post("/refresh")
def refresh_session(body: RefreshRequest, db: Session = Depends(get_db)):
    """Refreshes an access token using a valid refresh token."""
    try:
        return refresh_user_session(db, body.refresh_token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "REFRESH_FAILED", "message": str(e)},
        )


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    principal: UserPrincipal = Depends(require("view", "auth")),
    db: Session = Depends(get_db),
):
    """Revokes the active session token and clears auth cookies."""
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    if principal.session_jti:
        revoke_session(db, principal.session_jti)

    response.delete_cookie("access_token")

    log_audit_event(
        db=db,
        action="logout",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
        correlation_id=correlation_id,
        ip_address=ip,
        user_agent=ua,
    )

    return {"status": "logged_out", "message": "Session successfully revoked"}


@router.get("/me")
def get_me(principal: UserPrincipal = Depends(require("view", "user_profile"))):
    """Returns the authenticated principal's profile, roles, permissions, data scope, and synthetic status."""
    return {
        "user_id": principal.user_id,
        "email": principal.email,
        "roles": principal.roles,
        "permissions": principal.permissions,
        "data_scope": principal.data_scope.model_dump(),
        "is_service_account": principal.is_service_account,
        "is_synthetic": principal.is_synthetic,
    }
