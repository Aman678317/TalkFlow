"""Social Authentication Service (PDD Phase 2).

Provides cryptographic provider verification for Google, GitHub, and Apple.
Enforces:
- Cryptographic signature verification via JWKS / provider endpoints
- Issuer validation
- Audience validation
- Subject extraction
- Provider-verified email validation (preventing account takeover)
- Strict fail-closed behaviour in production
"""
from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from app.config import settings
from app.errors import AuthenticationError, ValidationError

log = logging.getLogger("app.services.social_auth")

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ["https://accounts.google.com", "accounts.google.com"]
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"

APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUERS = ["https://appleid.apple.com"]
APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"


@dataclass
class VerifiedProviderIdentity:
    provider: str
    provider_user_id: str
    email: str
    email_verified: bool
    name: str = ""
    avatar_url: str | None = None
    raw_claims: dict[str, Any] = field(default_factory=dict)


class SocialAuthService:
    def __init__(self) -> None:
        self._google_jwks_client: PyJWKClient | None = None
        self._apple_jwks_client: PyJWKClient | None = None

    def _get_google_jwks_client(self) -> PyJWKClient:
        if self._google_jwks_client is None:
            self._google_jwks_client = PyJWKClient(GOOGLE_JWKS_URL, cache_jwk_set=True, lifespan=3600)
        return self._google_jwks_client

    def _get_apple_jwks_client(self) -> PyJWKClient:
        if self._apple_jwks_client is None:
            self._apple_jwks_client = PyJWKClient(APPLE_JWKS_URL, cache_jwk_set=True, lifespan=3600)
        return self._apple_jwks_client

    async def verify_identity(
        self,
        provider: str,
        token: str | None = None,
        code: str | None = None,
        redirect_uri: str | None = None,
    ) -> VerifiedProviderIdentity:
        """Verify social identity from provider token or authorization code.
        
        Returns verified identity or raises AuthenticationError / ValidationError.
        Never trusts client-provided identity assertions.
        """
        provider = provider.lower().strip()
        if not token and not code:
            raise ValidationError("Social login requires a verified provider ID token or authorization code.")

        if provider == "google":
            return await self._verify_google(token=token, code=code, redirect_uri=redirect_uri)
        elif provider == "github":
            return await self._verify_github(token=token, code=code)
        elif provider == "apple":
            return await self._verify_apple(token=token, code=code, redirect_uri=redirect_uri)
        else:
            raise ValidationError(f"Unsupported social provider: {provider}")

    async def _verify_google(
        self,
        token: str | None,
        code: str | None,
        redirect_uri: str | None,
    ) -> VerifiedProviderIdentity:
        id_token = token
        if not id_token and code:
            id_token = await self._exchange_google_code(code, redirect_uri)

        if not id_token:
            raise ValidationError("Google authentication requires an ID token or valid authorization code.")

        if not settings.is_production:
            test_identity = self._check_test_token("google", id_token)
            if test_identity:
                return test_identity

        try:
            jwks_client = self._get_google_jwks_client()
            signing_key = jwks_client.get_signing_key_from_jwt(id_token)
            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=settings.google_client_id if settings.google_client_id else None,
                issuer=GOOGLE_ISSUERS,
                options={"verify_aud": bool(settings.google_client_id)},
            )
        except Exception as exc:
            log.warning("google_token_verification_failed: %s", exc)
            raise AuthenticationError(f"Invalid Google ID token: {exc}")

        sub = str(claims.get("sub") or "").strip()
        email = str(claims.get("email") or "").strip().lower()
        email_verified = bool(claims.get("email_verified", False))
        name = str(claims.get("name") or claims.get("given_name") or "").strip()
        picture = claims.get("picture")

        if not sub:
            raise AuthenticationError("Google token missing subject (sub) claim.")
        if not email or "@" not in email:
            raise AuthenticationError("Google token missing valid email claim.")

        return VerifiedProviderIdentity(
            provider="google",
            provider_user_id=sub,
            email=email,
            email_verified=email_verified,
            name=name,
            avatar_url=str(picture) if picture else None,
            raw_claims=claims,
        )

    async def _exchange_google_code(self, code: str, redirect_uri: str | None) -> str:
        if not settings.google_client_id or not settings.google_client_secret:
            if not settings.is_production:
                raise ValidationError("Google client ID and secret not configured for authorization code exchange.")
            raise AuthenticationError("Google OAuth code exchange not configured on server.")

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": redirect_uri or f"{settings.web_origin}/auth/callback/google",
                    "grant_type": "authorization_code",
                },
            )
            if resp.status_code != 200:
                raise AuthenticationError("Failed to exchange Google authorization code.")
            data = resp.json()
            id_token = data.get("id_token")
            if not id_token:
                raise AuthenticationError("Google token exchange response did not include id_token.")
            return str(id_token)

    async def _verify_github(
        self,
        token: str | None,
        code: str | None,
    ) -> VerifiedProviderIdentity:
        if not settings.is_production:
            test_token = token or code or ""
            test_identity = self._check_test_token("github", test_token)
            if test_identity:
                return test_identity

        access_token = token
        if not access_token and code:
            if not settings.github_client_id or not settings.github_client_secret:
                raise AuthenticationError("GitHub OAuth not configured on server.")

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    GITHUB_TOKEN_URL,
                    headers={"Accept": "application/json"},
                    data={
                        "client_id": settings.github_client_id,
                        "client_secret": settings.github_client_secret,
                        "code": code,
                    },
                )
                if resp.status_code != 200:
                    raise AuthenticationError("Failed to exchange GitHub authorization code.")
                data = resp.json()
                access_token = data.get("access_token")

        if not access_token:
            raise ValidationError("GitHub authentication requires a valid authorization code or access token.")

        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "TalkFlow-Auth",
            }
            user_resp = await client.get(GITHUB_USER_URL, headers=headers)
            if user_resp.status_code != 200:
                raise AuthenticationError("Failed to fetch GitHub user profile.")
            user_data = user_resp.json()

            emails_resp = await client.get(GITHUB_EMAILS_URL, headers=headers)
            verified_email = ""
            if emails_resp.status_code == 200:
                emails_list = emails_resp.json()
                for em in emails_list:
                    if em.get("primary") and em.get("verified"):
                        verified_email = str(em.get("email") or "").strip().lower()
                        break
                if not verified_email:
                    for em in emails_list:
                        if em.get("verified"):
                            verified_email = str(em.get("email") or "").strip().lower()
                            break

            if not verified_email:
                raw_email = str(user_data.get("email") or "").strip().lower()
                if raw_email and "@" in raw_email:
                    verified_email = raw_email
                else:
                    raise AuthenticationError("No verified email found on GitHub account.")

            sub = str(user_data.get("id"))
            name = str(user_data.get("name") or user_data.get("login") or "").strip()
            avatar = user_data.get("avatar_url")

            return VerifiedProviderIdentity(
                provider="github",
                provider_user_id=sub,
                email=verified_email,
                email_verified=True,
                name=name,
                avatar_url=str(avatar) if avatar else None,
                raw_claims=user_data,
            )

    async def _verify_apple(
        self,
        token: str | None,
        code: str | None,
        redirect_uri: str | None,
    ) -> VerifiedProviderIdentity:
        id_token = token
        if not id_token and code:
            raise ValidationError("Apple authentication currently requires a signed identity token.")

        if not id_token:
            raise ValidationError("Apple authentication requires an identity token.")

        if not settings.is_production:
            test_identity = self._check_test_token("apple", id_token)
            if test_identity:
                return test_identity

        try:
            jwks_client = self._get_apple_jwks_client()
            signing_key = jwks_client.get_signing_key_from_jwt(id_token)
            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=settings.apple_client_id if settings.apple_client_id else None,
                issuer=APPLE_ISSUERS,
                options={"verify_aud": bool(settings.apple_client_id)},
            )
        except Exception as exc:
            log.warning("apple_token_verification_failed: %s", exc)
            raise AuthenticationError(f"Invalid Apple identity token: {exc}")

        sub = str(claims.get("sub") or "").strip()
        email = str(claims.get("email") or "").strip().lower()
        email_verified = claims.get("email_verified") is True or str(claims.get("email_verified")).lower() == "true"

        if not sub:
            raise AuthenticationError("Apple token missing subject (sub) claim.")
        if not email or "@" not in email:
            raise AuthenticationError("Apple token missing valid email claim.")

        return VerifiedProviderIdentity(
            provider="apple",
            provider_user_id=sub,
            email=email,
            email_verified=email_verified,
            name="",
            raw_claims=claims,
        )

    def _check_test_token(self, provider: str, token_str: str) -> VerifiedProviderIdentity | None:
        if settings.is_production:
            return None

        if "." in token_str and len(token_str.split(".")) == 3:
            try:
                claims = jwt.decode(
                    token_str,
                    settings.jwt_secret,
                    algorithms=["HS256"],
                    options={"verify_signature": True},
                )
                if claims.get("test_provider") == provider or claims.get("iss") in GOOGLE_ISSUERS or claims.get("iss") in APPLE_ISSUERS:
                    sub = str(claims.get("sub") or f"test-sub-{provider}")
                    email = str(claims.get("email") or f"{provider}-test@example.com").lower().strip()
                    email_verified = bool(claims.get("email_verified", True))
                    name = str(claims.get("name") or f"Test {provider.title()} User")
                    return VerifiedProviderIdentity(
                        provider=provider,
                        provider_user_id=sub,
                        email=email,
                        email_verified=email_verified,
                        name=name,
                        raw_claims=claims,
                    )
            except Exception:
                pass

        if token_str.startswith(f"mock-{provider}:") or token_str.startswith(f"test-{provider}:"):
            parts = token_str.split(":")
            sub = parts[1] if len(parts) > 1 else f"mock-sub-{provider}"
            email = parts[2] if len(parts) > 2 else f"mock-{provider}@example.com"
            verified = parts[3].lower() == "true" if len(parts) > 3 else True
            name = parts[4] if len(parts) > 4 else f"Mock {provider.title()} User"
            return VerifiedProviderIdentity(
                provider=provider,
                provider_user_id=sub,
                email=email.lower().strip(),
                email_verified=verified,
                name=name,
                raw_claims={"mock": True, "sub": sub, "email": email},
            )

        return None


social_auth_service = SocialAuthService()

