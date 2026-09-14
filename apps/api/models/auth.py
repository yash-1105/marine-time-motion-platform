from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from .base import BaseModel


class Role(BaseModel):
    __tablename__ = "role"
    __table_args__ = {"schema": "config"}

    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)


class Permission(BaseModel):
    __tablename__ = "permission"
    __table_args__ = {"schema": "config"}

    action = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)


class RolePermission(BaseModel):
    __tablename__ = "role_permission"
    __table_args__ = {"schema": "config"}

    role_id = Column(UUID(as_uuid=True), ForeignKey("config.role.id", ondelete="CASCADE"), nullable=False)
    permission_id = Column(UUID(as_uuid=True), ForeignKey("config.permission.id", ondelete="CASCADE"), nullable=False)


class User(BaseModel):
    __tablename__ = "user"
    __table_args__ = {"schema": "config"}

    email = Column(String, nullable=False, unique=True)
    full_name = Column(String, nullable=False)
    tenant_id = Column(String, nullable=False, default="default-tenant")
    port_id = Column(String, nullable=True)
    terminal_id = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_synthetic = Column(Boolean, default=True, nullable=False)


class UserRole(BaseModel):
    __tablename__ = "user_role"
    __table_args__ = {"schema": "config"}

    user_id = Column(UUID(as_uuid=True), ForeignKey("config.user.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("config.role.id", ondelete="CASCADE"), nullable=False)


class ServiceAccount(BaseModel):
    __tablename__ = "service_account"
    __table_args__ = {"schema": "config"}

    client_id = Column(String, nullable=False, unique=True)
    client_secret_hash = Column(String, nullable=False)
    name = Column(String, nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("config.role.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(String, nullable=False, default="default-tenant")
    port_id = Column(String, nullable=True)
    terminal_id = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)


class SessionRecord(BaseModel):
    __tablename__ = "session"
    __table_args__ = {"schema": "config"}

    jti = Column(String, nullable=False, unique=True)
    user_id = Column(String, nullable=False)
    is_revoked = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    last_active_at = Column(DateTime(timezone=True), nullable=False)
