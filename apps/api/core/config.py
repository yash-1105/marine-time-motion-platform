from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Environment
    environment: str = "development"

    # Database & Cache
    database_url: str = "postgresql://admin:password@localhost:5434/marine_platform"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = ""
    upload_max_bytes: int = 25 * 1024 * 1024
    # The deployment mounts its governed object-store adapter (GCS/MinIO in
    # production; a local directory in development) at this path. Originals are
    # immutable evidence and are never read from the browser temp directory.
    ingestion_storage_path: str = "/tmp/marine-platform-uploads"

    @field_validator("database_url", mode="before")
    @classmethod
    def assemble_db_url(cls, v: str) -> str:
        if isinstance(v, str) and v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql://", 1)
        return v

    # OIDC / Microsoft Entra ID compatible configuration
    oidc_client_id: str = "marine-platform-client"
    oidc_client_secret: str = "oidc-client-secret-dev"
    oidc_issuer_url: str = "https://login.microsoftonline.com/common/v2.0"
    oidc_authorize_url: str = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    oidc_token_url: str = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    oidc_redirect_uri: str = "http://localhost:3000/auth/callback"
    oidc_scopes: str = "openid profile email"

    # JWT Session Configuration
    jwt_secret_key: str = "marine-platform-secure-jwt-secret-key-development"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 hours
    refresh_token_expire_days: int = 7
    session_idle_timeout_minutes: int = 1440  # 24 hours
    session_absolute_timeout_hours: int = 24
    cookie_secure: bool = False  # True in production HTTPS
    cookie_samesite: str = "lax"

    # AI (Gemini API via Google AI/Vertex). Model name is config, never hard-coded in business logic.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # Report artifact storage. Local paths are used in development; deployment supplies
    # an object-storage mounted/adapter path (MinIO/GCS deployment configuration).
    report_storage_path: str = "/tmp/marine-platform-reports"
    application_version: str = "1.0.0"

    # Copilot provider credentials are backend-only. The browser never receives these values.
    sarvam_api_key: str = ""
    sarvam_model: str = "sarvam-105b"

    @model_validator(mode="after")
    def require_production_secrets(self):
        if self.environment != "development":
            weak = len(self.jwt_secret_key) < 32 or self.jwt_secret_key in {"change-me", "marine-platform-secure-jwt-secret-key-development"}
            if weak:
                raise ValueError("JWT_SECRET_KEY must be a unique 32+ character secret outside development")
            if not self.cors_origins:
                raise ValueError("CORS_ORIGINS must list exact trusted origins outside development")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true outside development")
        return self


settings = Settings()
