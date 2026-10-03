"""Twilio Voice Access Token Service.

Generates RFC 7519 / Twilio-FPA compliant JWT Access Tokens for the Twilio Voice
JavaScript SDK (@twilio/voice-sdk). Grants incoming audio capabilities and connects
outbound calls to the configured or auto-provisioned TwiML App.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import httpx
import jwt

from app.config import settings

log = logging.getLogger("app.telephony.twilio_token")

_cached_api_key: dict[str, str] | None = None
_cached_twiml_app_sid: str | None = None


class TwilioTokenService:
    """Mints short-lived Voice Access Tokens for browser human agents."""

    @classmethod
    async def get_or_provision_api_key(cls) -> tuple[str, str]:
        """Resolve or provision API Key SID (SK...) and API Secret."""
        global _cached_api_key

        # 1. Configured via environment/.env
        if settings.twilio_api_key_sid and settings.twilio_api_key_secret:
            return settings.twilio_api_key_sid, settings.twilio_api_key_secret

        # 2. Check in-memory cache
        if _cached_api_key:
            return _cached_api_key["sid"], _cached_api_key["secret"]

        account_sid = settings.twilio_account_sid.strip()
        auth_token = settings.twilio_auth_token.strip()

        if not account_sid or not auth_token:
            # Dev mock fallback
            mock_sid = f"SK{uuid.uuid4().hex}"
            mock_secret = uuid.uuid4().hex
            return mock_sid, mock_secret

        # 3. Provision via Twilio REST API
        try:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Keys.json"
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    url,
                    data={"FriendlyName": "GlobalTalk AI Voice Client"},
                    auth=(account_sid, auth_token),
                )
                if res.status_code in (200, 201):
                    data = res.json()
                    sid = data.get("sid", "")
                    secret = data.get("secret", "")
                    if sid and secret:
                        _cached_api_key = {"sid": sid, "secret": secret}
                        log.info("Auto-provisioned new Twilio API Key: %s", sid)
                        return sid, secret
                else:
                    log.warning("Twilio Keys API returned status %s: %s", res.status_code, res.text)
        except Exception as exc:
            log.warning("Could not auto-provision Twilio API Key via REST API: %s", exc)

        # Fallback: Use account_sid as key_sid and auth_token as secret for HS256 signing
        return account_sid, auth_token

    @classmethod
    async def get_or_provision_twiml_app(cls, webhook_base_url: str = "") -> str:
        """Resolve or provision TwiML Application SID (AP...)."""
        global _cached_twiml_app_sid

        # 1. Configured via environment/.env
        if settings.twilio_twiml_app_sid:
            return settings.twilio_twiml_app_sid

        # 2. In-memory cache
        if _cached_twiml_app_sid:
            return _cached_twiml_app_sid

        account_sid = settings.twilio_account_sid.strip()
        auth_token = settings.twilio_auth_token.strip()

        if not account_sid or not auth_token:
            return f"AP{uuid.uuid4().hex}"

        base_url = (
            webhook_base_url
            or settings.telephony_webhook_base_url
            or f"http://127.0.0.1:{settings.api_port}"
        ).rstrip("/")
        voice_url = f"{base_url}/api/v1/telephony/webhooks/voice"
        status_url = f"{base_url}/api/v1/telephony/webhooks/status"

        try:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Applications.json"
            async with httpx.AsyncClient(timeout=10.0) as client:
                # First check existing applications
                list_res = await client.get(url, auth=(account_sid, auth_token))
                if list_res.status_code == 200:
                    apps = list_res.json().get("applications", [])
                    for app in apps:
                        if "GlobalTalk" in app.get("friendly_name", ""):
                            app_sid = app.get("sid", "")
                            if app_sid:
                                _cached_twiml_app_sid = app_sid
                                log.info("Found existing GlobalTalk TwiML App: %s", app_sid)
                                return app_sid

                # If not found, create new application
                create_res = await client.post(
                    url,
                    data={
                        "FriendlyName": "GlobalTalk AI Voice App",
                        "VoiceUrl": voice_url,
                        "VoiceMethod": "POST",
                        "StatusCallback": status_url,
                        "StatusCallbackMethod": "POST",
                    },
                    auth=(account_sid, auth_token),
                )
                if create_res.status_code in (200, 201):
                    app_data = create_res.json()
                    app_sid = app_data.get("sid", "")
                    if app_sid:
                        _cached_twiml_app_sid = app_sid
                        log.info("Auto-provisioned GlobalTalk TwiML App: %s", app_sid)
                        return app_sid
                else:
                    log.warning("Twilio Applications API returned %s: %s", create_res.status_code, create_res.text)
        except Exception as exc:
            log.warning("Could not auto-provision Twilio TwiML App: %s", exc)

        fallback_app = f"AP{account_sid[:30]}"
        return fallback_app

    @classmethod
    async def generate_voice_token(
        cls,
        *,
        identity: str | None = None,
        ttl_seconds: int = 3600,
        webhook_base_url: str = "",
    ) -> dict[str, Any]:
        """Mint a signed Twilio Voice Access Token.

        Returns:
            dict containing token string, identity, account_sid, twiml_app_sid, expires_in
        """
        agent_identity = identity or settings.twilio_agent_identity or "human_agent"
        account_sid = settings.twilio_account_sid.strip() or f"AC{uuid.uuid4().hex}"

        signing_sid, signing_secret = await cls.get_or_provision_api_key()
        twiml_app_sid = await cls.get_or_provision_twiml_app(webhook_base_url)

        now = int(time.time())
        exp = now + ttl_seconds

        headers = {
            "cty": "twilio-fpa;v=1",
            "typ": "JWT",
            "alg": "HS256",
        }

        token_id = f"{signing_sid}-{now}-{uuid.uuid4().hex[:8]}"

        payload: dict[str, Any] = {
            "jti": token_id,
            "iss": signing_sid,
            "sub": account_sid,
            "nbf": now,
            "exp": exp,
            "grants": {
                "identity": agent_identity,
                "voice": {
                    "incoming": {
                        "allow": True,
                    },
                    "outgoing": {
                        "application_sid": twiml_app_sid,
                    },
                },
            },
        }

        encoded_token = jwt.encode(payload, signing_secret, algorithm="HS256", headers=headers)
        if isinstance(encoded_token, bytes):
            encoded_token = encoded_token.decode("utf-8")

        return {
            "token": encoded_token,
            "identity": agent_identity,
            "account_sid": account_sid,
            "twiml_app_sid": twiml_app_sid,
            "phone_number": settings.twilio_phone_number,
            "expires_in": ttl_seconds,
            "created_at": now,
        }
