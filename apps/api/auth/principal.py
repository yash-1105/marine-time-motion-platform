from pydantic import BaseModel, Field

from apps.api.auth.scope import DataScope


class UserPrincipal(BaseModel):
    """Represents an authenticated principal (User or Service Account) within a request context."""

    user_id: str = Field(..., description="Unique identifier of user or service account")
    email: str = Field(..., description="Email address or service account identifier")
    roles: list[str] = Field(default_factory=list, description="List of assigned roles")
    permissions: list[str] = Field(default_factory=list, description="List of action permissions")
    data_scope: DataScope = Field(..., description="Tenant, port, and terminal scope")
    is_service_account: bool = Field(False, description="True if machine/service credential")
    is_synthetic: bool = Field(True, description="True if operating in synthetic tenant")
    session_jti: str | None = Field(None, description="Unique session identifier for revocation")

    def has_permission(self, action: str) -> bool:
        """Checks if principal has the specified action permission."""
        # Platform Administrator possesses all permissions
        if "Platform Administrator" in self.roles:
            return True
        return action in self.permissions

    def has_role(self, role_name: str) -> bool:
        """Checks if principal has the specified role."""
        return role_name in self.roles
