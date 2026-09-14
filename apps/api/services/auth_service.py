from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from apps.api.core.config import settings
from apps.api.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_pkce_pair,
    verify_secret,
)
from apps.api.models.auth import (
    Permission,
    Role,
    RolePermission,
    ServiceAccount,
    SessionRecord,
    User,
    UserRole,
)


def get_oidc_authorization_url(state: str) -> tuple[str, str]:
    """Generates an OIDC authorization URL with PKCE (Microsoft Entra ID compatible).

    Returns (authorization_url, code_verifier).
    """
    code_verifier, code_challenge = generate_pkce_pair()
    params = {
        "client_id": settings.oidc_client_id,
        "response_type": "code",
        "redirect_uri": settings.oidc_redirect_uri,
        "response_mode": "query",
        "scope": settings.oidc_scopes,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    url = f"{settings.oidc_authorize_url}?{urlencode(params)}"
    return url, code_verifier


def create_user_session(
    db: Session,
    user_id: str,
    email: str,
    roles: list[str],
    permissions: list[str],
    data_scope: dict[str, Any],
    is_service_account: bool = False,
) -> dict[str, Any]:
    """Creates a new user session with access and refresh tokens and stores session state."""
    access_token, access_jti, access_exp = create_access_token(
        subject=user_id,
        email=email,
        roles=roles,
        permissions=permissions,
        data_scope=data_scope,
        is_service_account=is_service_account,
    )
    refresh_token, refresh_jti, refresh_exp = create_refresh_token(subject=user_id)

    # Record active session in DB
    now = datetime.now(UTC)
    session_record = SessionRecord(
        jti=access_jti,
        user_id=user_id,
        is_revoked=False,
        expires_at=access_exp,
        last_active_at=now,
    )
    db.add(session_record)
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": int((access_exp - now).total_seconds()),
        "roles": roles,
        "permissions": permissions,
        "data_scope": data_scope,
        "session_id": access_jti,
    }


def refresh_user_session(db: Session, refresh_token_str: str) -> dict[str, Any]:
    """Validates refresh token and issues a new access token while checking timeouts."""
    payload = decode_token(refresh_token_str)
    if payload.get("type") != "refresh":
        raise ValueError("Invalid token type for refresh")

    user_id = payload["sub"]
    user = db.query(User).filter_by(id=user_id, is_active=True).first()
    if not user:
        raise ValueError("User not found or inactive")

    # Fetch user roles and permissions
    roles = db.query(Role.name).join(UserRole, UserRole.role_id == Role.id).filter(UserRole.user_id == user.id).all()
    role_names = [r[0] for r in roles]

    perms = (
        db.query(Permission.action)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user.id)
        .all()
    )
    perm_actions = list({p[0] for p in perms})

    data_scope = {
        "tenant_id": user.tenant_id,
        "port_id": user.port_id,
        "terminal_id": user.terminal_id,
    }

    return create_user_session(
        db=db,
        user_id=str(user.id),
        email=user.email,
        roles=role_names,
        permissions=perm_actions,
        data_scope=data_scope,
        is_service_account=False,
    )


def revoke_session(db: Session, jti: str) -> bool:
    """Revokes an active session by token JTI."""
    record = db.query(SessionRecord).filter_by(jti=jti).first()
    if record:
        record.is_revoked = True
        db.commit()
        return True
    return False


def is_session_active(db: Session, jti: str) -> bool:
    """Checks whether a session token has been revoked or exceeded idle/absolute timeouts."""
    record = db.query(SessionRecord).filter_by(jti=jti).first()
    if not record:
        # Service accounts or stateless tokens if not tracked
        return True

    if record.is_revoked:
        return False

    now = datetime.now(UTC)
    # Check idle timeout
    idle_delta = timedelta(minutes=settings.session_idle_timeout_minutes)
    if record.last_active_at and (now - record.last_active_at) > idle_delta:
        record.is_revoked = True
        db.commit()
        return False

    # Check absolute expiration
    if record.expires_at and now > record.expires_at:
        record.is_revoked = True
        db.commit()
        return False

    # Update last active timestamp
    record.last_active_at = now
    db.commit()
    return True


def authenticate_service_account(db: Session, client_id: str, client_secret: str) -> dict[str, Any] | None:
    """Authenticates a service account by client_id and hashed client_secret."""
    sa = db.query(ServiceAccount).filter_by(client_id=client_id, is_active=True).first()
    if not sa:
        return None

    if sa.expires_at and datetime.now(UTC) > sa.expires_at:
        return None

    if not verify_secret(client_secret, sa.client_secret_hash):
        return None

    role = db.query(Role).filter_by(id=sa.role_id).first()
    role_name = role.name if role else "Integration Service Account"

    perms = (
        db.query(Permission.action)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .filter(RolePermission.role_id == sa.role_id)
        .all()
    )
    perm_actions = [p[0] for p in perms]

    data_scope = {
        "tenant_id": sa.tenant_id,
        "port_id": sa.port_id,
        "terminal_id": sa.terminal_id,
    }

    return create_user_session(
        db=db,
        user_id=str(sa.id),
        email=sa.name,
        roles=[role_name],
        permissions=perm_actions,
        data_scope=data_scope,
        is_service_account=True,
    )
