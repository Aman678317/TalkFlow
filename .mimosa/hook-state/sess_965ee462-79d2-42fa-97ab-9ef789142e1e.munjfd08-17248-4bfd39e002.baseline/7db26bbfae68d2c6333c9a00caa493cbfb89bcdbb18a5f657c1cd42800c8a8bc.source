"""Security primitives: password hashing (bcrypt), JWT access/refresh,
API-key generation/hashing, CSRF tokens. No plaintext passwords, ever.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
import jwt

from app.config import settings
from app.errors import AuthenticationError

TokenType = Literal["access", "refresh"]


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"),
                         bcrypt.gensalt(rounds=settings.bcrypt_rounds)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def password_policy_ok(password: str) -> tuple[bool, str]:
    if len(password) < 8:
        return False, "Password must be at least 8 characters."
    if len(password) > 256:
        return False, "Password must be at most 256 characters."
    has_alpha = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    if not (has_alpha and has_digit):
        return False, "Password must contain both letters and numbers."
    return True, ""


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #

def create_token(subject: str, token_type: TokenType, *,
                 extra: dict[str, Any] | None = None,
                 ttl_seconds: int | None = None) -> tuple[str, str]:
    """Returns (token, jti)."""
    now = datetime.now(timezone.utc)
    if ttl_seconds is None:
        ttl_seconds = (settings.jwt_access_ttl_minutes * 60 if token_type == "access"
                       else settings.jwt_refresh_ttl_days * 86400)
    jti = uuid.uuid4().hex
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
        "iss": "globaltalk-ai",
    }
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, jti


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret,
                             algorithms=[settings.jwt_algorithm],
                             issuer="globaltalk-ai",
                             options={"require": ["exp", "sub", "type"]})
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Session expired. Please sign in again.")
    except jwt.InvalidTokenError as e:
        raise AuthenticationError("Invalid authentication token.")
    if payload.get("type") != expected_type:
        raise AuthenticationError("Wrong token type.")
    return payload


# --------------------------------------------------------------------------- #
# API keys — gt_live_<40 hex>; only SHA-256 hash + prefix stored
# --------------------------------------------------------------------------- #

def generate_api_key() -> tuple[str, str, str]:
    """Returns (plaintext_key, key_hash, prefix). Plaintext shown once."""
    raw = secrets.token_hex(20)
    key = f"gt_live_{raw}"
    return key, hash_api_key(key), key[:12]


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def verify_api_key_hash(key: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(key), stored_hash)


# --------------------------------------------------------------------------- #
# Webhook signatures
# --------------------------------------------------------------------------- #

def sign_webhook_payload(secret: str, timestamp: int, body: bytes) -> str:
    """HMAC-SHA256 over '<timestamp>.<body>' (Stripe-style)."""
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return f"v1={mac.hexdigest()}"


def verify_webhook_signature(secret: str, timestamp: int, body: bytes,
                             signature: str, tolerance_s: int = 300) -> bool:
    expected = sign_webhook_payload(secret, timestamp, body)
    if abs(time.time() - timestamp) > tolerance_s:
        return False
    return hmac.compare_digest(expected, signature)


# --------------------------------------------------------------------------- #
# CSRF (double-submit token bound to session)
# --------------------------------------------------------------------------- #

def generate_csrf_token(session_ref: str) -> str:
    mac = hmac.new(settings.secret_key.encode(), session_ref.encode(), hashlib.sha256)
    return mac.hexdigest()[:32]


def verify_csrf_token(session_ref: str, token: str) -> bool:
    return hmac.compare_digest(generate_csrf_token(session_ref), token or "")


# --------------------------------------------------------------------------- #
# Realtime session tickets (short-lived, single-purpose; PDD §14.1: browser
# never receives long-lived inference keys)
# --------------------------------------------------------------------------- #

def create_session_ticket(session_id: str, participant_id: str,
                          ttl_s: int = 120) -> str:
    token, _ = create_token(
        session_id, "access",
        extra={"purpose": "rt_ticket", "pid": participant_id},
        ttl_seconds=ttl_s)
    return token


def verify_session_ticket(ticket: str) -> tuple[str, str]:
    """Returns (session_id, participant_id)."""
    payload = decode_token(ticket, "access")
    if payload.get("purpose") != "rt_ticket":
        raise AuthenticationError("Invalid realtime ticket.")
    return payload["sub"], payload["pid"]
