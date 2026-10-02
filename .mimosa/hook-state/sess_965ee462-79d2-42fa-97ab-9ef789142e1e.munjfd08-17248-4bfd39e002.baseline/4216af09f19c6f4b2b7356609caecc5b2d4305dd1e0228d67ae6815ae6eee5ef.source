"""Security primitives: password hashing (bcrypt), JWT access/refresh, API-key hashing, tokens."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
import jwt

from globaltalk.core.config import settings
from globaltalk.core.errors import UnauthorizedError


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    payload = {
        "sub": subject,
        "type": "access",
        "iat": int(_now().timestamp()),
        "exp": int((_now() + timedelta(minutes=settings.access_token_ttl_minutes)).timestamp()),
        "jti": secrets.token_hex(8),
        **(extra or {}),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str, session_id: str) -> tuple[str, str]:
    """Returns (token, token_hash). Only the hash is stored server-side."""
    jti = secrets.token_hex(16)
    payload = {
        "sub": subject, "type": "refresh", "sid": session_id, "jti": jti,
        "iat": int(_now().timestamp()),
        "exp": int((_now() + timedelta(days=settings.refresh_token_ttl_days)).timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, sha256(token)


def decode_token(token: str, expected_type: Literal["access", "refresh"] = "access") -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Token expired", code="token_expired", recoverable=True)
    except jwt.InvalidTokenError:
        raise UnauthorizedError("Invalid token", code="token_invalid")
    if payload.get("type") != expected_type:
        raise UnauthorizedError("Wrong token type", code="token_type")
    return payload


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Returns (full_key, prefix, key_hash). The full key is shown exactly once."""
    secret = secrets.token_urlsafe(32)
    full = f"gtk_{secret}"
    return full, full[:12], sha256(full)


def generate_webhook_signing_secret() -> str:
    return "whsec_" + secrets.token_urlsafe(24)


def webhook_signature(payload_bytes: bytes, secret: str, timestamp: int) -> str:
    msg = f"{timestamp}.".encode() + payload_bytes
    return "v1=" + hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def random_token(nbytes: int = 24) -> str:
    return secrets.token_urlsafe(nbytes)


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
