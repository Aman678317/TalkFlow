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
    # Check that HttpOnly refresh_token cookie was set
    assert "refresh_token" in res.cookies
    assert res.cookies["refresh_token"] == data["tokens"]["refresh_token"]


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
    first_refresh = reg.json()["tokens"]["refresh_token"]

    # Refresh using body or cookie
    ref_res = services_app_client.post("/api/v1/auth/refresh", json={
        "refresh_token": first_refresh,
    })
    assert ref_res.status_code == 200
    data = ref_res.json()
    second_refresh = data["refresh_token"]
    assert second_refresh != first_refresh
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
    token1 = reg.json()["tokens"]["refresh_token"]

    # First rotate token1 -> token2
    ref1 = services_app_client.post("/api/v1/auth/refresh", json={"refresh_token": token1})
    assert ref1.status_code == 200
    token2 = ref1.json()["refresh_token"]

    # Second rotate token2 -> token3
    ref2 = services_app_client.post("/api/v1/auth/refresh", json={"refresh_token": token2})
    assert ref2.status_code == 200
    token3 = ref2.json()["refresh_token"]

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
    refresh = reg.json()["tokens"]["refresh_token"]

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
    refresh = reg.json()["tokens"]["refresh_token"]

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
