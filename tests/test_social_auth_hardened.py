"""Phase 2 — Real Social Authentication Verification & Hardening Tests.

Validates:
1. Social login requires cryptographically verifiable provider credential (token/code).
2. Forged/invalid provider credentials fail with 401.
3. Client-supplied body email/name cannot override verified provider claims.
4. Account takeover protection: unverified provider email cannot link to existing account.
5. UserIdentity record is created and linked to internal user and provider subject.
6. Identity management endpoints (/me/identities, DELETE /me/identities/{provider}).
"""
import uuid
import pytest
from app.config import settings


def test_social_login_rejects_missing_credential(services_app_client):
    res = services_app_client.post("/api/v1/auth/social-login", json={
        "provider": "google",
    })
    assert res.status_code in (400, 422)


def test_social_login_rejects_unsupported_provider(services_app_client):
    res = services_app_client.post("/api/v1/auth/social-login", json={
        "provider": "unsupported_provider",
        "token": "some-token",
    })
    assert res.status_code == 422


def test_social_login_rejects_forged_or_invalid_jwt(services_app_client):
    res = services_app_client.post("/api/v1/auth/social-login", json={
        "provider": "google",
        "token": "header.invalid_forged_payload.bad_signature",
    })
    assert res.status_code == 401


def test_social_login_provisions_new_user_and_identity(services_app_client):
    sub_id = f"google-sub-{uuid.uuid4().hex[:12]}"
    email = f"verified_{uuid.uuid4().hex[:8]}@gmail.com"
    mock_token = f"mock-google:{sub_id}:{email}:true:Google Verified User"

    res = services_app_client.post("/api/v1/auth/social-login", json={
        "provider": "google",
        "token": mock_token,
        # Even if attacker sends a different email in body, verified token must win
        "email": "victim_ignored@example.com",
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["user"]["email"] == email
    assert data["user"]["name"] == "Google Verified User"
    assert "access_token" in data["tokens"]
    assert "refresh_token" in res.cookies
    assert "csrf_token" in res.cookies

    # Query identities for this user
    access = data["tokens"]["access_token"]
    id_res = services_app_client.get(
        "/api/v1/auth/me/identities",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert id_res.status_code == 200
    identities = id_res.json()
    assert len(identities) == 1
    assert identities[0]["provider"] == "google"
    assert identities[0]["provider_user_id"] == sub_id
    assert identities[0]["email"] == email
    assert identities[0]["email_verified"] is True


def test_social_login_resolves_existing_identity(services_app_client):
    sub_id = f"google-sub-{uuid.uuid4().hex[:12]}"
    email = f"user_{uuid.uuid4().hex[:8]}@gmail.com"
    mock_token = f"mock-google:{sub_id}:{email}:true:Original Name"

    # 1. First login creates user
    res1 = services_app_client.post("/api/v1/auth/social-login", json={
        "provider": "google",
        "token": mock_token,
    })
    assert res1.status_code == 200
    user_id_1 = res1.json()["user"]["id"]

    # 2. Second login with same provider subject returns existing user
    res2 = services_app_client.post("/api/v1/auth/social-login", json={
        "provider": "google",
        "token": mock_token,
    })
    assert res2.status_code == 200
    user_id_2 = res2.json()["user"]["id"]
    assert user_id_1 == user_id_2


def test_account_takeover_prevented_on_unverified_email(services_app_client):
    # Create target account via password registration
    target_email = f"target_{uuid.uuid4().hex[:8]}@example.com"
    reg = services_app_client.post("/api/v1/auth/signup", json={
        "email": target_email,
        "password": "ValidPassword123!",
        "name": "Target Account Owner",
        "organization_name": "Target Org",
    })
    assert reg.status_code == 201

    # Attacker attempts to login with a provider token that has NOT verified the email
    sub_id = f"attacker-sub-{uuid.uuid4().hex[:12]}"
    unverified_token = f"mock-google:{sub_id}:{target_email}:false:Attacker Impersonator"

    attack_res = services_app_client.post("/api/v1/auth/social-login", json={
        "provider": "google",
        "token": unverified_token,
    })
    # MUST FAIL: Unverified provider email cannot link to existing account
    assert attack_res.status_code == 401
    err_body = attack_res.json()
    err_text = (err_body.get("message") or err_body.get("detail") or err_body.get("error", {}).get("message", "")).lower()
    assert "not verified" in err_text


def test_account_linking_when_provider_verified(services_app_client):
    # Create target account via standard registration
    target_email = f"verified_owner_{uuid.uuid4().hex[:8]}@example.com"
    reg = services_app_client.post("/api/v1/auth/signup", json={
        "email": target_email,
        "password": "ValidPassword123!",
        "name": "Legitimate Owner",
        "organization_name": "Owner Org",
    })
    assert reg.status_code == 201
    registered_id = reg.json()["user"]["id"]

    # Legitimate owner logs in via Google with a verified email
    sub_id = f"owner-google-sub-{uuid.uuid4().hex[:12]}"
    verified_token = f"mock-google:{sub_id}:{target_email}:true:Legitimate Owner"

    link_res = services_app_client.post("/api/v1/auth/social-login", json={
        "provider": "google",
        "token": verified_token,
    })
    assert link_res.status_code == 200
    linked_id = link_res.json()["user"]["id"]
    assert linked_id == registered_id

    # Verify identity is now listed under the user
    access = link_res.json()["tokens"]["access_token"]
    id_res = services_app_client.get(
        "/api/v1/auth/me/identities",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert id_res.status_code == 200
    identities = id_res.json()
    assert any(i["provider"] == "google" and i["provider_user_id"] == sub_id for i in identities)

    # Test unlinking identity
    unlink_res = services_app_client.delete(
        "/api/v1/auth/me/identities/google",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert unlink_res.status_code == 204

    # Verify identity is now removed
    id_res2 = services_app_client.get(
        "/api/v1/auth/me/identities",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert id_res2.status_code == 200
    assert not any(i["provider"] == "google" for i in id_res2.json())

