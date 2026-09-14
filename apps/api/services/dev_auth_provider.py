from typing import Any

from sqlalchemy.orm import Session

from apps.api.core.config import settings
from apps.api.models.auth import Permission, Role, RolePermission, User, UserRole


def verify_dev_provider_allowed() -> None:
    """Refuses development authentication provider if ENVIRONMENT != 'development'."""
    if settings.environment != "development":
        raise RuntimeError(
            f"Development authentication provider is strictly forbidden when ENVIRONMENT != 'development'. Current: '{settings.environment}'"
        )


def get_dev_users(db: Session) -> list[dict[str, Any]]:
    """Returns the list of seeded users available for rapid development authentication."""
    verify_dev_provider_allowed()
    users = db.query(User).filter_by(is_active=True).all()
    results = []
    for user in users:
        roles = (
            db.query(Role.name).join(UserRole, UserRole.role_id == Role.id).filter(UserRole.user_id == user.id).all()
        )
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

        results.append(
            {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "roles": role_names,
                "permissions": perm_actions,
                "tenant_id": user.tenant_id,
                "port_id": user.port_id,
                "terminal_id": user.terminal_id,
                "is_synthetic": user.is_synthetic,
            }
        )
    return results


def authenticate_dev_user(db: Session, role_or_email: str) -> dict[str, Any] | None:
    """Authenticates a development user by role name or email."""
    verify_dev_provider_allowed()
    user = db.query(User).filter((User.email == role_or_email) | (User.full_name.ilike(f"%{role_or_email}%"))).first()

    if not user:
        # Try finding by role
        role = db.query(Role).filter(Role.name.ilike(role_or_email)).first()
        if role:
            ur = db.query(UserRole).filter_by(role_id=role.id).first()
            if ur:
                user = db.query(User).filter_by(id=ur.user_id).first()

    if not user:
        return None

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

    return {
        "user_id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "roles": role_names,
        "permissions": perm_actions,
        "data_scope": {
            "tenant_id": user.tenant_id,
            "port_id": user.port_id,
            "terminal_id": user.terminal_id,
        },
        "is_synthetic": user.is_synthetic,
    }
