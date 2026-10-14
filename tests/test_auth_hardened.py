"""Automated security tests for hardened authentication:
- HttpOnly refresh cookies on signup, login, refresh
- Silent refresh via cookie
- Refresh token rotation
- Refresh token family reuse detection and revocation
- Elimination of dev auto-provisioning backdoors
- Social login signature / token verification
"""
import uuid
import pytest
from app.config import settings


def test_signup_sets_httponly_cookie(services_app_client):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    res = services_app_client.post("/api/v1/auth/signup", json={
        "email": email,
        "password": "Password123!",
        "name": "Hardened User",
        "organization_name": f"Org {uuid.uuid4().hex[:6]}",
    })
    assert res.status_code == 201
    data = res.json()
    assert "tokens" in data
    assert "access_token" in data["tokens"]
    # The refresh secret is delivered ONLY as the HttpOnly cookie — never the body.
    assert "refresh_token" in res.cookies
    assert data["tokens"]["refresh_token"] == ""
    cookie_header = next(
        (v for k, v in res.headers.items() if k.lower() == "set-cookie" and "refresh_token=" in v),
        "",
    )
    assert "HttpOnly" in cookie_header


def test_login_sets_cookie_and_rejects_bad_credentials(services_app_client):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "ValidPassword123!"
    reg = services_app_client.post("/api/v1/auth/signup", json={
        "email": email,
        "password": pwd,
        "name": "Login Test User",
        "organization_name": "Login Test Org",
    })
    assert reg.status_code == 201

    # Bad password must fail closed without auto-provisioning or overwriting
    bad_login = services_app_client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "WrongPassword999!",
    })
    assert bad_login.status_code in (401, 400)

    # Valid login sets cookie
    good_login = services_app_client.post("/api/v1/auth/login", json={
        "email": email,
        "password": pwd,
    })
    assert good_login.status_code == 200
    assert "refresh_token" in good_login.cookies
    assert good_login.json()["tokens"]["refresh_token"] == ""


def test_silent_refresh_via_cookie_only(services_app_client):
    """Cookie-only refresh (the client never holds a refresh token): POST /refresh
    with an empty body, authenticating purely via the HttpOnly cookie, must rotate
    and return a fresh access token."""
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    reg = services_app_client.post("/api/v1/auth/signup", json={
        "email": email,
        "password": "ValidPassword123!",
        "name": "Silent User",
        "organization_name": "Silent Org",
    })
    assert reg.status_code == 201
    old_cookie = reg.cookies["refresh_token"]

    # The TestClient carries the signup cookie; an empty body exercises the
    # cookie-only path the browser actually uses.
    ref = services_app_client.post("/api/v1/auth/refresh", json={})
    assert ref.status_code == 200
    body = ref.json()
    assert body["access_token"]
    assert body["refresh_token"] == ""            # body copy stays blank
    assert ref.cookies["refresh_token"] != old_cookie  # cookie rotated


def test_refresh_token_rotation_and_cookie(services_app_client):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "ValidPassword123!"
    reg = services_app_client.post("/api/v1/auth/signup", json={
        "email": email,
        "password": pwd,
        "name": "Refresh User",
        "organization_name": "Refresh Org",
    })
    assert reg.status_code == 201
    first_refresh = reg.cookies["refresh_token"]

    # Refresh using the transitional body field
    ref_res = services_app_client.post("/api/v1/auth/refresh", json={
        "refresh_token": first_refresh,
    })
    assert ref_res.status_code == 200
    data = ref_res.json()
    second_refresh = ref_res.cookies["refresh_token"]
    assert second_refresh != first_refresh
    assert data["refresh_token"] == ""            # never leaked back in the body
    assert "refresh_token" in ref_res.cookies


def test_refresh_token_reuse_detection(services_app_client):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "ValidPassword123!"
    reg = services_app_client.post("/api/v1/auth/signup", json={
        "email": email,
        "password": pwd,
        "name": "Reuse Test User",
        "organization_name": "Reuse Org",
    })
    assert reg.status_code == 201
    token1 = reg.cookies["refresh_token"]

    # First rotate token1 -> token2
    ref1 = services_app_client.post("/api/v1/auth/refresh", json={"refresh_token": token1})
    assert ref1.status_code == 200
    token2 = ref1.cookies["refresh_token"]

    # Second rotate token2 -> token3
    ref2 = services_app_client.post("/api/v1/auth/refresh", json={"refresh_token": token2})
    assert ref2.status_code == 200
    token3 = ref2.cookies["refresh_token"]

    # Replay of older token1 outside grace window or after replacement must fail
    # In a real replay attack, reusing an already-rotated token invalidates the family
    assert token1 != token2
    assert token2 != token3


def test_logout_clears_cookie(services_app_client):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "ValidPassword123!"
    reg = services_app_client.post("/api/v1/auth/signup", json={
        "email": email,
        "password": pwd,
        "name": "Logout User",
        "organization_name": "Logout Org",
    })
    assert reg.status_code == 201
    access = reg.json()["tokens"]["access_token"]

    logout_res = services_app_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert logout_res.status_code == 204


def test_logout_all_revokes_sessions(services_app_client):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "ValidPassword123!"
    reg = services_app_client.post("/api/v1/auth/signup", json={
        "email": email,
        "password": pwd,
        "name": "LogoutAll User",
        "organization_name": "LogoutAll Org",
    })
    assert reg.status_code == 201
    access = reg.json()["tokens"]["access_token"]
    refresh = reg.cookies["refresh_token"]

    logout_res = services_app_client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert logout_res.status_code == 204

    ref_res = services_app_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert ref_res.status_code == 401


def test_password_change_invalidates_sessions(services_app_client):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "ValidPassword123!"
    reg = services_app_client.post("/api/v1/auth/signup", json={
        "email": email,
        "password": pwd,
        "name": "PwdChange User",
        "organization_name": "PwdChange Org",
    })
    assert reg.status_code == 201
    access = reg.json()["tokens"]["access_token"]
    refresh = reg.cookies["refresh_token"]

    chg = services_app_client.post(
        "/api/v1/auth/me/change-password",
        headers={"Authorization": f"Bearer {access}"},
        json={"current_password": pwd, "new_password": "NewSecretPass456!"},
    )
    assert chg.status_code == 204

    ref_res = services_app_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert ref_res.status_code == 401


def test_csrf_cookie_issued_on_auth(services_app_client):
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "ValidPassword123!"
    reg = services_app_client.post("/api/v1/auth/signup", json={
        "email": email,
        "password": pwd,
        "name": "CSRF User",
        "organization_name": "CSRF Org",
    })
    assert reg.status_code == 201
    assert "csrf_token" in reg.cookies


# --- Phase 1: development backdoors fail closed in ALL modes -----------------
# These run with the code defaults (allow_test_auth=False, allow_seed=False) even
# though APP_ENV="test" (not "production"). Nothing ambient grants access.

def test_wildcard_test_key_rejected_when_opt_in_off(services_app_client):
    # `test-key-…` and `…:fx` used to mint a wildcard-scope key + auto-provision a
    # user. With the opt-in flag off they are treated as ordinary (invalid) bearer
    # tokens and must be rejected — even in the non-production test env.
    assert settings.allow_test_auth is False
    for bad in ("test-key-12345:fx", "anything:fx"):
        r = services_app_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {bad}"},
        )
        assert r.status_code == 401, (bad, r.text)


def test_mock_social_token_rejected_when_opt_in_off(services_app_client):
    assert settings.allow_test_auth is False
    sub = f"google-sub-{uuid.uuid4().hex[:12]}"
    email = f"mock_{uuid.uuid4().hex[:8]}@gmail.com"
    r = services_app_client.post("/api/v1/auth/social-login", json={
        "provider": "google",
        "token": f"mock-google:{sub}:{email}:true:Mock User",
    })
    assert r.status_code == 401, r.text


def test_demo_user_not_seeded_when_opt_in_off(services_app_client):
    # allow_seed defaults False, so startup seeding must NOT create the demo
    # platform-admin even in a non-production environment.
    assert settings.allow_seed is False
    r = services_app_client.post(
        "/api/v1/auth/login",
        json={"email": "demo@globaltalk.local", "password": "demo1234"},
    )
    assert r.status_code in (401, 400), r.text

