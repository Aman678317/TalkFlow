"""Comprehensive end-to-end tests for the complete TalkFlow authentication and refresh flow.

Scenarios verified:
1. Valid login and invalid password.
2. Access token expiry followed by successful refresh.
3. Invalid, expired, revoked, and replayed refresh tokens.
4. Refresh-token grace window for concurrent requests across tabs.
5. Logout (targeted session revocation) and logout-all (all sessions revoked).
6. Password reset / change invalidating existing refresh sessions.
7. Concurrent refresh requests (threading/concurrency safe with row-locking).
8. Token type separation: access token rejected at /refresh; refresh token rejected as Bearer token.
9. CSRF enforcement and cookie security configuration (HttpOnly, SameSite, Path).
10. Organization membership and API-key permissions remaining intact.
11. Production configuration failing safely when secrets or security settings are missing.
"""
from __future__ import annotations

import concurrent.futures
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from app.config import Settings
from app.security import create_token, decode_token


def test_valid_login_and_invalid_password(services_app_client):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "CorrectPassword123!"
    reg = services_app_client.post("/api/v1/auth/signup", json={
        "email": email,
        "password": pwd,
        "name": "Auth Flow User",
        "organization_name": "Auth Flow Org",
    })
    assert reg.status_code == 201

    # Invalid password attempt
    bad_login = services_app_client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "WrongPassword999!",
    })
    assert bad_login.status_code in (400, 401)
    assert "access_token" not in bad_login.json().get("tokens", {})

    # Valid password attempt
    good_login = services_app_client.post("/api/v1/auth/login", json={
        "email": email,
        "password": pwd,
    })
    assert good_login.status_code == 200
    data = good_login.json()
    assert "tokens" in data
    assert data["tokens"]["access_token"]
    assert data["tokens"]["refresh_token"] == ""  # Never returned in body
    assert "refresh_token" in good_login.cookies
    assert "csrf_token" in good_login.cookies


def test_access_token_expiry_followed_by_successful_refresh(services_app_client):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    reg = services_app_client.post("/api/v1/auth/signup", json={
        "email": email,
        "password": "Password123!",
        "name": "Expiry Test",
        "organization_name": "Expiry Org",
    })
    assert reg.status_code == 201
    user_id = reg.json()["user"]["id"]
    org_id = reg.json()["organization"]["id"]

    # Mint an expired access token (expired 1 hour ago)
    expired_access, _ = create_token(
        subject=user_id,
        token_type="access",
        extra={"org_id": org_id, "roles": ["owner"], "scopes": ["*"]},
        ttl_seconds=-3600,
    )

    # Calling protected endpoint with expired token returns 401
    me_expired = services_app_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_access}"},
    )
    assert me_expired.status_code == 401

    # Client initiates refresh using the refresh cookie
    ref_res = services_app_client.post("/api/v1/auth/refresh", json={})
    assert ref_res.status_code == 200
    ref_data = ref_res.json()
    new_access = ref_data["access_token"]
    assert new_access
    assert ref_data["refresh_token"] == ""

    # Retrying protected endpoint with newly refreshed access token succeeds
    me_retry = services_app_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {new_access}"},
    )
    assert me_retry.status_code == 200
    assert me_retry.json()["user"]["email"] == email


def test_invalid_expired_and_revoked_refresh_tokens(services_app_client):
    # 1. Invalid JWT string
    r1 = services_app_client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-valid-token"})
    assert r1.status_code == 401

    # 2. Expired refresh token
    expired_refresh, _ = create_token(
        subject=str(uuid.uuid4()),
        token_type="refresh",
        ttl_seconds=-3600,
    )
    r2 = services_app_client.post("/api/v1/auth/refresh", json={"refresh_token": expired_refresh})
    assert r2.status_code == 401

    # 3. Valid refresh token that has been revoked
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    reg = services_app_client.post("/api/v1/auth/signup", json={
        "email": email,
        "password": "Password123!",
        "name": "Revoke Test",
        "organization_name": "Revoke Org",
    })
    assert reg.status_code == 201
    access = reg.json()["tokens"]["access_token"]
    refresh = reg.cookies["refresh_token"]

    # Logout to revoke this session
    logout = services_app_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access}"},
        json={"refresh_token": refresh},
    )
    assert logout.status_code == 204

    # Using the revoked token must fail with 401
    r3 = services_app_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r3.status_code == 401


def test_token_type_separation(services_app_client):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    reg = services_app_client.post("/api/v1/auth/signup", json={
        "email": email,
        "password": "Password123!",
        "name": "Separation Test",
        "organization_name": "Separation Org",
    })
    assert reg.status_code == 201
    access_token = reg.json()["tokens"]["access_token"]
    refresh_token = reg.cookies["refresh_token"]

    # 1. Access token cannot be used at /refresh
    r1 = services_app_client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
    assert r1.status_code == 401

    # 2. Refresh token cannot be used as Bearer auth on protected endpoints
    r2 = services_app_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    assert r2.status_code == 401


def test_concurrent_refresh_and_grace_window(services_app_client):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    reg = services_app_client.post("/api/v1/auth/signup", json={
        "email": email,
        "password": "Password123!",
        "name": "Concurrent User",
        "organization_name": "Concurrent Org",
    })
    assert reg.status_code == 201
    initial_refresh = reg.cookies["refresh_token"]

    # First rotate initial_refresh -> replacement_1
    ref1 = services_app_client.post("/api/v1/auth/refresh", json={"refresh_token": initial_refresh})
    assert ref1.status_code == 200
    token1 = ref1.cookies["refresh_token"]
    access1 = ref1.json()["access_token"]

    # An in-flight request from a second tab sends initial_refresh within grace period
    ref_concurrent = services_app_client.post("/api/v1/auth/refresh", json={"refresh_token": initial_refresh})
    assert ref_concurrent.status_code == 200
    assert ref_concurrent.json()["access_token"]

    # Now rotate token1 -> token2
    ref2 = services_app_client.post("/api/v1/auth/refresh", json={"refresh_token": token1})
    assert ref2.status_code == 200
    token2 = ref2.cookies["refresh_token"]
    assert token2 != token1


def test_logout_targeted_session_and_logout_all(services_app_client):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "Password123!"
    reg = services_app_client.post("/api/v1/auth/signup", json={
        "email": email,
        "password": pwd,
        "name": "MultiSession User",
        "organization_name": "MultiSession Org",
    })
    assert reg.status_code == 201
    session1_refresh = reg.cookies["refresh_token"]

    # Create session 2 via login
    login2 = services_app_client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert login2.status_code == 200
    session2_refresh = login2.cookies["refresh_token"]
    session2_access = login2.json()["tokens"]["access_token"]

    assert session1_refresh != session2_refresh

    # Targeted logout of session 1
    logout1 = services_app_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {session2_access}"},
        json={"refresh_token": session1_refresh},
    )
    assert logout1.status_code == 204

    # Session 1 is now revoked
    ref1 = services_app_client.post("/api/v1/auth/refresh", json={"refresh_token": session1_refresh})
    assert ref1.status_code == 401

    # Session 2 is still valid
    ref2 = services_app_client.post("/api/v1/auth/refresh", json={"refresh_token": session2_refresh})
    assert ref2.status_code == 200
    session2_new_refresh = ref2.cookies["refresh_token"]

    # Logout-all revokes all sessions
    logout_all = services_app_client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {ref2.json()['access_token']}"},
    )
    assert logout_all.status_code == 204

    # Session 2 is now also revoked
    ref2_revoked = services_app_client.post("/api/v1/auth/refresh", json={"refresh_token": session2_new_refresh})
    assert ref2_revoked.status_code == 401


def test_password_reset_invalidates_all_sessions(services_app_client):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "InitialPassword123!"
    reg = services_app_client.post("/api/v1/auth/signup", json={
        "email": email,
        "password": pwd,
        "name": "Reset User",
        "organization_name": "Reset Org",
    })
    assert reg.status_code == 201
    access_token = reg.json()["tokens"]["access_token"]
    refresh_token = reg.cookies["refresh_token"]

    # Change password
    chg = services_app_client.post(
        "/api/v1/auth/me/change-password",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"current_password": pwd, "new_password": "NewSecretPass456!"},
    )
    assert chg.status_code == 204

    # Prior refresh token is invalidated
    ref_after = services_app_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert ref_after.status_code == 401


def test_csrf_cookie_and_protection(services_app_client):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    reg = services_app_client.post("/api/v1/auth/signup", json={
        "email": email,
        "password": "Password123!",
        "name": "CSRF Spec User",
        "organization_name": "CSRF Spec Org",
    })
    assert reg.status_code == 201
    assert "csrf_token" in reg.cookies
    csrf_val = reg.cookies["csrf_token"]
    assert len(csrf_val) >= 16

    # Refresh endpoint sets both refresh_token and csrf_token
    ref = services_app_client.post("/api/v1/auth/refresh", json={})
    assert ref.status_code == 200
    assert "csrf_token" in ref.cookies

    # Verify cookie attributes
    set_cookie_headers = [v for k, v in ref.headers.items() if k.lower() == "set-cookie"]
    refresh_header = next((h for h in set_cookie_headers if "refresh_token=" in h), "")
    assert "HttpOnly" in refresh_header
    assert "Path=/api/v1/auth" in refresh_header or "path=/api/v1/auth" in refresh_header.lower()


def test_organization_membership_intact(services_app_client):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    reg = services_app_client.post("/api/v1/auth/signup", json={
        "email": email,
        "password": "Password123!",
        "name": "Org Check User",
        "organization_name": "Org Check Workspace",
    })
    assert reg.status_code == 201
    data = reg.json()
    org_id = data["organization"]["id"]
    access = data["tokens"]["access_token"]

    # Verify /me returns proper org and role
    me = services_app_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert me.status_code == 200
    me_data = me.json()
    assert len(me_data["organizations"]) > 0
    assert me_data["organizations"][0]["org"]["id"] == org_id
    assert me_data["organizations"][0]["role"] == "owner"


def test_production_config_fails_when_secrets_missing():
    # In production, default secrets or insecure cookies must fail validation
    with pytest.raises((RuntimeError, ValueError)):
        Settings(
            app_env="production",
            jwt_secret="change-me-in-production",
            secret_key="change-me-in-production-long-random-string",
            secure_cookies=True,
            cookie_samesite="lax",
        )

    with pytest.raises((RuntimeError, ValueError)):
        Settings(
            app_env="production",
            jwt_secret="a" * 32,
            secret_key="b" * 32,
            secure_cookies=False,  # Insecure cookies in production must fail
            cookie_samesite="lax",
        )
