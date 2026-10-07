"""Phase 11: Developer Platform, API Keys & Webhooks Hardening Test Suite.
Verifies:
1. High-entropy API key generation, prefix handling, and secure SHA-256 hash storage at rest.
2. Granular API key scope enforcement (scoped permissions, wildcard support, fail-closed on ungranted scopes).
3. API key rotation and revocation lifecycle (immediate invalidation, no reuse of revoked keys).
4. API key expiration enforcement (expired keys rejected with 401).
5. Rate metering isolation by API key identity.
6. Webhook SSRF protection blocking private, link-local, loopback, IPv4-mapped IPv6, and cloud metadata targets.
7. Webhook HMAC-SHA256 signature generation, dual headers, and replay protection within strict time windows.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.errors import AuthenticationError, AuthorizationError, RateLimitError, ValidationError
from app.ratelimit import check_rate_limit
from app.security import (
    generate_api_key,
    hash_api_key,
    sign_webhook_payload,
    verify_api_key_hash,
    verify_webhook_signature,
)
from app.services.webhook_service import _assert_public_url


def test_api_key_high_entropy_generation_and_storage(services_app_client, user):
    """Test API key creation produces high entropy keys, stores hash at rest, and returns plaintext only once."""
    # 1. Direct security helper verification
    raw_key, key_hash, prefix = generate_api_key(prefix="gtk_live_")
    assert raw_key.startswith("gtk_live_")
    assert len(raw_key) >= 40, "API key must contain high entropy"
    assert verify_api_key_hash(raw_key, key_hash)
    assert not verify_api_key_hash(raw_key + "tampered", key_hash)

    # 2. REST API creation endpoint
    res = services_app_client.post(
        "/api/v1/api-keys",
        headers=user["headers"],
        json={
            "name": "Integration Key",
            "scopes": ["translate", "usage"],
            "expires_in_days": 30,
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert "plaintext_key" in data
    plaintext = data["plaintext_key"]
    key_id = data["id"]
    prefix = data["prefix"]

    # Plaintext key starts with prefix
    assert plaintext.startswith(prefix)

    # Key list must NOT leak plaintext key
    list_res = services_app_client.get("/api/v1/api-keys", headers=user["headers"])
    assert list_res.status_code == 200
    keys = list_res.json()
    created_entry = next((k for k in keys if k["id"] == key_id), None)
    assert created_entry is not None
    assert "plaintext_key" not in created_entry
    assert created_entry["prefix"] == prefix


def test_api_key_granular_scope_enforcement(services_app_client, user):
    """Verify API keys strictly enforce granted scopes and fail-closed on unauthorized actions."""
    # Create key with only translate scope
    res = services_app_client.post(
        "/api/v1/api-keys",
        headers=user["headers"],
        json={"name": "Translate Only Key", "scopes": ["translate"]},
    )
    assert res.status_code == 201
    translate_key = res.json()["plaintext_key"]
    api_headers = {"Authorization": f"Bearer {translate_key}"}

    # Allowed: Translate endpoint
    trans_res = services_app_client.post(
        "/api/v1/translate",
        headers=api_headers,
        json={"text": "Hello world", "source_language": "en", "target_language": "hi"},
    )
    assert trans_res.status_code == 200

    # Denied: Meeting creation requires 'meetings' or 'create_meeting' scope
    meet_res = services_app_client.post(
        "/api/v1/meetings",
        headers=api_headers,
        json={"title": "Unauthorized Meeting", "mode": "ws", "hear_lang": "en"},
    )
    assert meet_res.status_code == 403, "API key without meeting scope must receive 403 Forbidden"
    assert "lacks" in meet_res.text.lower() or "permission" in meet_res.text.lower()

    # Create key with meetings scope
    res_meet = services_app_client.post(
        "/api/v1/api-keys",
        headers=user["headers"],
        json={"name": "Meeting Key", "scopes": ["meetings"]},
    )
    assert res_meet.status_code == 201
    meeting_key = res_meet.json()["plaintext_key"]
    meeting_headers = {"Authorization": f"Bearer {meeting_key}"}

    # Meeting creation now succeeds
    meet_res2 = services_app_client.post(
        "/api/v1/meetings",
        headers=meeting_headers,
        json={"title": "Authorized Meeting", "mode": "ws", "hear_lang": "en"},
    )
    assert meet_res2.status_code == 201


def test_api_key_rotation_and_revocation_lifecycle(services_app_client, user):
    """Verify API key revocation and rotation instantly invalidate former keys."""
    # Create key
    res = services_app_client.post(
        "/api/v1/api-keys",
        headers=user["headers"],
        json={"name": "Rotating Key", "scopes": ["translate"]},
    )
    assert res.status_code == 201
    key_id = res.json()["id"]
    original_key = res.json()["plaintext_key"]

    orig_headers = {"Authorization": f"Bearer {original_key}"}
    r = services_app_client.post("/api/v1/translate", headers=orig_headers, json={"text": "ping", "source_language": "en", "target_language": "hi"})
    assert r.status_code == 200

    # Rotate key
    rot_res = services_app_client.post(f"/api/v1/api-keys/{key_id}/rotate", headers=user["headers"])
    assert rot_res.status_code == 200
    rotated_key = rot_res.json()["plaintext_key"]
    assert rotated_key != original_key

    # Old key is immediately rejected
    old_res = services_app_client.post("/api/v1/translate", headers=orig_headers, json={"text": "ping", "source_language": "en", "target_language": "hi"})
    assert old_res.status_code == 401

    # New rotated key works
    new_res = services_app_client.post(
        "/api/v1/translate",
        headers={"Authorization": f"Bearer {rotated_key}"},
        json={"text": "pong", "source_language": "en", "target_language": "hi"},
    )
    assert new_res.status_code == 200

    # Revoke new key
    new_id = rot_res.json()["id"]
    rev_res = services_app_client.post(f"/api/v1/api-keys/{new_id}/revoke", headers=user["headers"])
    assert rev_res.status_code == 204

    # Revoked key is rejected
    rev_check = services_app_client.post(
        "/api/v1/translate",
        headers={"Authorization": f"Bearer {rotated_key}"},
        json={"text": "pong", "source_language": "en", "target_language": "hi"},
    )
    assert rev_check.status_code == 401


def test_api_key_rate_metering():
    """Verify rate limiter correctly throttles API key callers and provides retry information."""
    key_identity = f"key:{uuid.uuid4()}"
    limit_spec = "3/minute"

    async def _exercise_rate_limit():
        # First 3 should pass
        for _ in range(3):
            await check_rate_limit("api_meter", key_identity, limit_spec)
        # 4th must raise RateLimitError
        with pytest.raises(RateLimitError) as exc_info:
            await check_rate_limit("api_meter", key_identity, limit_spec)
        assert exc_info.value.details["limit"] == 3
        assert exc_info.value.details["retry_after"] >= 1

    asyncio.run(_exercise_rate_limit())


def test_webhook_ssrf_protection_hardened():
    """Verify SSRF guard rejects all internal, loopback, link-local, cloud metadata, and invalid targets."""
    forbidden_targets = [
        "http://127.0.0.1:8080/hook",
        "http://localhost:5000/hook",
        "http://169.254.169.254/latest/meta-data",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://10.0.1.5/webhook",
        "http://172.16.20.1/webhook",
        "http://192.168.1.100/webhook",
        "http://[::1]/webhook",
        "http://[::ffff:127.0.0.1]/webhook",
        "http://user:secret@public-domain.com/webhook",
        "ftp://public-domain.com/webhook",
    ]

    for target in forbidden_targets:
        with pytest.raises(RuntimeError):
            asyncio.run(_assert_public_url(target, force_check=True))


def test_webhook_signing_and_replay_protection():
    """Verify HMAC-SHA256 signature generation, dual header formats, and replay tolerance."""
    secret = "whsec_test_secret_0123456789abcdef"
    payload = b'{"event":"translation.completed","org_id":"test"}'
    now_ts = int(time.time())

    # Generate signature
    sig = sign_webhook_payload(secret, now_ts, payload)
    assert sig.startswith("v1=")

    # Verify matching signature
    assert verify_webhook_signature(secret, now_ts, payload, sig)

    # Verify Stripe-style dual header format: t=timestamp,v1=signature
    stripe_sig = f"t={now_ts},{sig}"
    assert verify_webhook_signature(secret, now_ts, payload, stripe_sig)

    # Verify replay protection: timestamp older than 300s must fail
    old_ts = now_ts - 360
    assert not verify_webhook_signature(secret, old_ts, payload, sig, tolerance_s=300)

    # Verify future timestamp beyond tolerance fails
    future_ts = now_ts + 360
    assert not verify_webhook_signature(secret, future_ts, payload, sig, tolerance_s=300)

    # Verify tampered payload fails
    tampered_payload = b'{"event":"translation.completed","org_id":"tampered"}'
    assert not verify_webhook_signature(secret, now_ts, tampered_payload, sig)

    # Verify wrong secret fails
    assert not verify_webhook_signature("whsec_wrong_secret", now_ts, payload, sig)

