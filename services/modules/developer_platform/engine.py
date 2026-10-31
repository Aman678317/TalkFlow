"""Developer Platform Engine (Module I).

Handles API key management, sliding-window rate limiting, audio usage metering,
signed time-limited download URLs, and webhook event dispatching.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple
import httpx

from modules.developer_platform.models import (
    ApiKeyRecord,
    WebhookDeliveryLog,
    WebhookRegistration,
)

logger = logging.getLogger("talkflow.modules.developer_platform")


class DeveloperPlatformEngine:
    """Core Developer Platform and API authentication coordinator."""

    def __init__(self, signing_secret: str = "talkflow_secure_sdk_signing_secret_key_prod") -> None:
        self.signing_secret = signing_secret
        # api_key_hash -> ApiKeyRecord
        self._keys: Dict[str, ApiKeyRecord] = {}
        # key_id -> List[timestamps] for rate limiting
        self._request_timestamps: Dict[str, List[float]] = {}
        # webhook_id -> WebhookRegistration
        self._webhooks: Dict[str, WebhookRegistration] = {}
        # delivery_id -> WebhookDeliveryLog
        self._webhook_logs: List[WebhookDeliveryLog] = []
        self._seed_default_dev_key()

    def _seed_default_dev_key(self) -> None:
        """Seed a standard local development key: 'tk_live_demo12345'."""
        raw_key = "tk_live_demo12345"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        self._keys[key_hash] = ApiKeyRecord(
            key_id="key_dev_default",
            api_key_hash=key_hash,
            name="TalkFlow Master Developer Key",
            tenant_id="org_default",
            role="admin",
            rate_limit_rpm=300,
            total_minutes_allowed=10000.0,
            total_minutes_used=12.5,
            total_requests_count=42,
        )

    def create_api_key(
        self,
        name: str,
        tenant_id: str = "org_default",
        role: str = "developer",
        rate_limit_rpm: int = 120,
        quota_minutes: float = 1000.0,
    ) -> Tuple[str, ApiKeyRecord]:
        """Generates a secure API key, stores its hash, and returns (plaintext_key, record)."""
        raw_token = f"tk_live_{secrets.token_hex(16)}"
        key_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        key_id = f"key_{secrets.token_hex(6)}"

        rec = ApiKeyRecord(
            key_id=key_id,
            api_key_hash=key_hash,
            name=name,
            tenant_id=tenant_id,
            role=role,
            rate_limit_rpm=rate_limit_rpm,
            total_minutes_allowed=quota_minutes,
        )
        self._keys[key_hash] = rec
        logger.info(f"Created developer API key '{key_id}' for tenant '{tenant_id}'")
        return raw_token, rec

    def authenticate_key(self, raw_key: str) -> Optional[ApiKeyRecord]:
        """Authenticates an API key string and verifies status and expiration."""
        if not raw_key:
            return None
        # Support Bearer or raw token
        clean_key = raw_key.replace("Bearer ", "").strip()
        key_hash = hashlib.sha256(clean_key.encode()).hexdigest()
        rec = self._keys.get(key_hash)
        if not rec or not rec.is_active:
            return None
        if rec.expires_at and time.time() > rec.expires_at:
            return None
        return rec

    def check_rate_limit_and_meter(self, rec: ApiKeyRecord, audio_minutes: float = 0.0) -> bool:
        """Verifies rate limits (RPM) and audio quota, updating usage counters."""
        now = time.time()
        window_start = now - 60.0

        ts_list = self._request_timestamps.setdefault(rec.key_id, [])
        # Evict timestamps older than 60s
        self._request_timestamps[rec.key_id] = [t for t in ts_list if t >= window_start]

        if len(self._request_timestamps[rec.key_id]) >= rec.rate_limit_rpm:
            logger.warning(f"Rate limit exceeded for key '{rec.key_id}' ({rec.rate_limit_rpm} RPM)")
            return False

        if rec.total_minutes_used + audio_minutes > rec.total_minutes_allowed:
            logger.warning(f"Quota exceeded for key '{rec.key_id}'")
            return False

        # Record request
        self._request_timestamps[rec.key_id].append(now)
        rec.total_requests_count += 1
        rec.total_minutes_used = round(rec.total_minutes_used + audio_minutes, 3)
        return True

    def generate_secure_download_url(self, file_path: str, expires_in_sec: int = 3600) -> str:
        """Generates a secure HMAC time-limited URL token."""
        expires = int(time.time()) + expires_in_sec
        sig_data = f"{file_path}:{expires}".encode()
        signature = hmac.new(self.signing_secret.encode(), sig_data, hashlib.sha256).hexdigest()[:16]
        return f"/api/v1/developer/downloads?file={file_path}&expires={expires}&sig={signature}"

    def verify_download_signature(self, file_path: str, expires: int, signature: str) -> bool:
        """Verifies time-limited secure download URL validity."""
        if time.time() > expires:
            return False
        sig_data = f"{file_path}:{expires}".encode()
        expected = hmac.new(self.signing_secret.encode(), sig_data, hashlib.sha256).hexdigest()[:16]
        return hmac.compare_digest(expected, signature)

    # --- Webhooks ---

    def register_webhook(
        self,
        target_url: str,
        event_types: Optional[List[str]] = None,
        tenant_id: str = "org_default",
    ) -> WebhookRegistration:
        wh_id = f"wh_{secrets.token_hex(6)}"
        sec = secrets.token_hex(16)
        ev_types = event_types or ["job.completed", "meeting.intelligence.ready"]

        wh = WebhookRegistration(
            webhook_id=wh_id,
            tenant_id=tenant_id,
            target_url=target_url,
            event_types=ev_types,
            secret_token=sec,
        )
        self._webhooks[wh_id] = wh
        return wh

    async def dispatch_webhook(self, event_type: str, payload: Dict[str, Any], tenant_id: str = "org_default") -> None:
        """Dispatches an asynchronous webhook notification to subscribed endpoints."""
        for wh in self._webhooks.values():
            if not wh.is_active or wh.tenant_id != tenant_id:
                continue
            if event_type in wh.event_types or "*" in wh.event_types:
                asyncio.create_task(self._deliver_webhook_worker(wh, event_type, payload))

    async def _deliver_webhook_worker(self, wh: WebhookRegistration, event_type: str, payload: Dict[str, Any]) -> None:
        del_id = f"del_{secrets.token_hex(8)}"
        status_code = None
        success = False
        try:
            headers = {
                "X-TalkFlow-Event": event_type,
                "X-TalkFlow-Signature": hmac.new(wh.secret_token.encode(), str(payload).encode(), hashlib.sha256).hexdigest(),
                "Content-Type": "application/json",
            }
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(wh.target_url, json=payload, headers=headers)
                status_code = res.status_code
                success = res.status_code in (200, 201, 202, 204)
        except Exception as e:
            logger.warning(f"Webhook delivery failed for '{wh.target_url}': {e}")

        self._webhook_logs.append(
            WebhookDeliveryLog(
                delivery_id=del_id,
                webhook_id=wh.webhook_id,
                event_type=event_type,
                payload=payload,
                response_code=status_code,
                success=success,
            )
        )


# Global Engine Instance
developer_platform_engine = DeveloperPlatformEngine()

