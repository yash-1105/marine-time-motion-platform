import base64
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from apps.api.core.config import settings


def generate_pkce_pair() -> tuple[str, str]:
    """Generates an RFC 7636 compliant PKCE code_verifier and code_challenge (S256)."""
    # code_verifier: high-entropy cryptographic random string (43 to 128 characters)
    code_verifier = secrets.token_urlsafe(64)
    # code_challenge: base64url(sha256(code_verifier)) without padding
    hashed = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(hashed).decode("ascii").rstrip("=")
    return code_verifier, code_challenge


def verify_pkce(code_verifier: str, code_challenge: str) -> bool:
    """Verifies that code_verifier matches the code_challenge."""
    hashed = hashlib.sha256(code_verifier.encode("ascii")).digest()
    expected_challenge = base64.urlsafe_b64encode(hashed).decode("ascii").rstrip("=")
    return secrets.compare_digest(expected_challenge, code_challenge)


def hash_secret(secret: str) -> str:
    """Hashes a secret for storage at rest (e.g. service account client secret)."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def verify_secret(raw_secret: str, stored_hash: str) -> bool:
    """Constant-time comparison of a secret against its stored hash."""
    hashed = hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()
    return secrets.compare_digest(hashed, stored_hash)


def create_access_token(
    subject: str,
    email: str,
    roles: list[str],
    permissions: list[str],
    data_scope: dict[str, Any],
    is_service_account: bool = False,
    expires_delta: timedelta | None = None,
    jti: str | None = None,
) -> tuple[str, str, datetime]:
    """Creates a signed JWT access token. Returns (token_string, jti, expire_datetime)."""
    now = datetime.now(UTC)
    delta = expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    expire = now + delta
    token_jti = jti or str(uuid.uuid4())

    payload = {
        "sub": subject,
        "email": email,
        "roles": roles,
        "permissions": permissions,
        "data_scope": data_scope,
        "is_service_account": is_service_account,
        "jti": token_jti,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, token_jti, expire


def create_refresh_token(
    subject: str,
    jti: str | None = None,
    expires_delta: timedelta | None = None,
) -> tuple[str, str, datetime]:
    """Creates a signed JWT refresh token. Returns (token_string, jti, expire_datetime)."""
    now = datetime.now(UTC)
    delta = expires_delta or timedelta(days=settings.refresh_token_expire_days)
    expire = now + delta
    token_jti = jti or str(uuid.uuid4())

    payload = {
        "sub": subject,
        "jti": token_jti,
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, token_jti, expire


def decode_token(token: str) -> dict[str, Any]:
    """Decodes and validates a JWT token."""
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid token: {e!s}")
