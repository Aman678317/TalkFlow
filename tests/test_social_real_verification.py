"""Phase 2 — REAL social provider verification (docs/PRODUCTION_ROADMAP.md §Phase 2).

These tests exercise the actual cryptographic paths with RS256-signed tokens and a
mocked JWKS source (no network): signature verification, iss/aud/exp validation,
fail-closed behaviour when a provider is unconfigured, Apple nonce replay defence,
and the rejection of client-asserted identity profiles.

The mock-token escape hatch (ALLOW_TEST_AUTH) stays OFF here — that is the point.
"""
import time
import types
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import settings
from app.services import social_auth_service as sas


@pytest.fixture(scope="module")
def rsa_keys():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv, serialization.load_pem_public_key(pub)


class _FakeJwksClient:
    """Stand-in for PyJWKClient: returns the test public key for any token."""

    def __init__(self, public_key):
        self._key = public_key

    def get_signing_key_from_jwt(self, token):
        return types.SimpleNamespace(key=self._key)


@pytest.fixture()
def google_jwks(rsa_keys):
    _, pub = rsa_keys
    prev = sas.social_auth_service._google_jwks_client
    sas.social_auth_service._google_jwks_client = _FakeJwksClient(pub)
    yield
    sas.social_auth_service._google_jwks_client = prev


@pytest.fixture()
def apple_jwks(rsa_keys):
    _, pub = rsa_keys
    prev = sas.social_auth_service._apple_jwks_client
    sas.social_auth_service._apple_jwks_client = _FakeJwksClient(pub)
    yield
    sas.social_auth_service._apple_jwks_client = prev


def _google_token(priv, *, aud="gt-web-app", iss="https://accounts.google.com", email=None, verified=True, exp=None):
    now = int(time.time())
    claims = {
        "iss": iss,
        "aud": aud,
        "sub": f"google-sub-{uuid.uuid4().hex[:10]}",
        "email": email or f"verified_{uuid.uuid4().hex[:8]}@gmail.com",
        "email_verified": verified,
        "name": "Real Google User",
        "iat": now,
        "exp": exp if exp is not None else now + 300,
    }
    return jwt.encode(claims, priv, algorithm="RS256"), claims


def _apple_token(priv, *, aud="gt-web-app", iss="https://appleid.apple.com", nonce=None):
    now = int(time.time())
    claims = {
        "iss": iss,
        "aud": aud,
        "sub": f"apple-sub-{uuid.uuid4().hex[:10]}",
        "email": f"user_{uuid.uuid4().hex[:8]}@privaterelay.appleid.com",
        "email_verified": "true",
        "iat": now,
        "exp": now + 300,
    }
    if nonce is not None:
        claims["nonce"] = nonce
    return jwt.encode(claims, priv, algorithm="RS256"), claims


@pytest.fixture()
def configured_providers(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "gt-web-app")
    monkeypatch.setattr(settings, "apple_client_id", "gt-web-app")
    monkeypatch.setattr(settings, "github_client_id", "")
    monkeypatch.setattr(settings, "github_client_secret", "")


def test_google_id_token_maps_deterministically(services_app_client, google_jwks, configured_providers, rsa_keys):
    priv, _ = rsa_keys
    token, claims = _google_token(priv)

    res = services_app_client.post("/api/v1/auth/social-login", json={"provider": "google", "token": token})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["user"]["email"] == claims["email"]
    assert data["user"]["email_verified"] is True
    assert data["tokens"]["refresh_token"] == ""          # cookie-only transport
    assert "refresh_token" in res.cookies

    # Same verified identity again → same user (deterministic mapping)
    res2 = services_app_client.post("/api/v1/auth/social-login", json={"provider": "google", "token": token})
    assert res2.status_code == 200
    assert res2.json()["user"]["id"] == data["user"]["id"]


def test_google_rejects_wrong_audience(services_app_client, google_jwks, configured_providers, rsa_keys):
    priv, _ = rsa_keys
    token, _ = _google_token(priv, aud="some-other-app")
    res = services_app_client.post("/api/v1/auth/social-login", json={"provider": "google", "token": token})
    assert res.status_code == 401


def test_google_rejects_wrong_issuer(services_app_client, google_jwks, configured_providers, rsa_keys):
    priv, _ = rsa_keys
    token, _ = _google_token(priv, iss="https://evil.example")
    res = services_app_client.post("/api/v1/auth/social-login", json={"provider": "google", "token": token})
    assert res.status_code == 401


def test_google_rejects_expired_token(services_app_client, google_jwks, configured_providers, rsa_keys):
    priv, _ = rsa_keys
    token, _ = _google_token(priv, exp=int(time.time()) - 60)
    res = services_app_client.post("/api/v1/auth/social-login", json={"provider": "google", "token": token})
    assert res.status_code == 401


def test_google_fails_closed_when_unconfigured(services_app_client, google_jwks, rsa_keys):
    # No google_client_id configured: even a perfectly signed token must be refused,
    # because the audience cannot be validated.
    priv, _ = rsa_keys
    token, _ = _google_token(priv)
    res = services_app_client.post("/api/v1/auth/social-login", json={"provider": "google", "token": token})
    assert res.status_code == 401
    assert "not configured" in res.json()["error"]["message"].lower()


def test_apple_nonce_mismatch_rejected(services_app_client, apple_jwks, configured_providers, rsa_keys):
    priv, _ = rsa_keys
    token, _ = _apple_token(priv, nonce="nonce-from-provider-session")
    res = services_app_client.post("/api/v1/auth/social-login", json={
        "provider": "apple", "token": token, "nonce": "different-nonce",
    })
    assert res.status_code == 401


def test_apple_nonce_match_accepted(services_app_client, apple_jwks, configured_providers, rsa_keys):
    priv, _ = rsa_keys
    nonce = f"n-{uuid.uuid4().hex}"
    token, claims = _apple_token(priv, nonce=nonce)
    res = services_app_client.post("/api/v1/auth/social-login", json={
        "provider": "apple", "token": token, "nonce": nonce,
    })
    assert res.status_code == 200, res.text
    assert res.json()["user"]["email"] == claims["email"]


def test_client_asserted_profile_without_credential_rejected(services_app_client):
    # Phase 2 acceptance: arbitrary email submissions are rejected. The schema no
    # longer even carries identity fields — a profile without a verified credential
    # is a 422, never an account.
    res = services_app_client.post("/api/v1/auth/social-login", json={
        "provider": "google",
        "email": "attacker@evil.example",
        "name": "Not A Real Person",
    })
    assert res.status_code in (400, 422), res.text


def test_github_code_exchange_fails_closed_when_unconfigured(services_app_client, configured_providers):
    res = services_app_client.post("/api/v1/auth/social-login", json={
        "provider": "github", "code": "looks-like-a-code",
    })
    assert res.status_code == 401
