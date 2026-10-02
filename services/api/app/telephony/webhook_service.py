"""Telephony Webhook Service: Processing carrier callbacks and TwiML stream negotiation."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import models as M
from app.errors import AuthorizationError
from app.telephony.base import WebhookEvent
from app.telephony.call_service import CallService
from app.telephony.security import TelephonySecurity
from app.telephony.service import get_telephony_service

log = logging.getLogger("app.telephony.webhook")


class TelephonyWebhookService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.telephony = get_telephony_service()

    async def handle_voice_webhook(
        self,
        headers: dict[str, str],
        payload: dict[str, Any],
        request_url: str,
        raw_body: bytes = b"",
    ) -> str:
        """Handle incoming call or call connection webhook by generating carrier TwiML."""
        # 1. Carrier signature verification (Phase 12 & 13 Security)
        is_valid, reason = TelephonySecurity.verify_webhook_request(headers, payload, request_url, raw_body)
        if not is_valid:
            log.warning("Voice webhook signature verification failed: %s", reason)
            raise AuthorizationError(f"Carrier signature verification failed: {reason}")

        provider = self.telephony.get_provider()
        event: WebhookEvent = provider.parse_webhook(headers, payload)

        call_sid = event.call_sid
        log.info("Received verified voice webhook for call %s (from=%s, to=%s, auth=%s)", call_sid, event.from_number, event.to_number, reason)

        cs = CallService(self.db)
        call_row = await cs.get_call_by_sid(call_sid)

        call_id_str = str(call_row.id) if call_row else "unknown"
        host_base = settings.telephony_webhook_base_url or request_url.rsplit("/api/", 1)[0]
        ws_scheme = "wss" if host_base.startswith("https") else "ws"
        host_netloc = host_base.split("://")[-1]
        stream_url = f"{ws_scheme}://{host_netloc}/ws/telephony/media/{call_id_str}"

        # Generate XML connecting call leg to bidirectional media stream
        custom_params = {
            "call_id": call_id_str,
            "caller_lang": call_row.caller_language if call_row else "en",
            "receiver_lang": call_row.receiver_language if call_row else "ja",
        }
        return provider.generate_twiml_stream_response(
            call_sid=call_sid,
            stream_url=stream_url,
            custom_params=custom_params,
        )

    async def handle_status_webhook(
        self,
        headers: dict[str, str],
        payload: dict[str, Any],
        request_url: str = "",
        raw_body: bytes = b"",
    ) -> None:
        """Process carrier status callback (ringing, in-progress, completed, failed, busy)."""
        is_valid, reason = TelephonySecurity.verify_webhook_request(headers, payload, request_url, raw_body)
        if not is_valid:
            log.warning("Status webhook signature verification failed: %s", reason)
            raise AuthorizationError(f"Carrier signature verification failed: {reason}")

        provider = self.telephony.get_provider()
        event: WebhookEvent = provider.parse_webhook(headers, payload)

        log.info("Call status webhook for %s: %s", event.call_sid, event.status.value)
        cs = CallService(self.db)
        dur = int(payload.get("CallDuration") or payload.get("duration") or 0)
        err = payload.get("ErrorMessage") or payload.get("error_message")

        await cs.transition_status(
            event.call_sid,
            event.status,
            duration_seconds=dur,
            error_message=err,
            extra_data=event.raw_data,
        )
