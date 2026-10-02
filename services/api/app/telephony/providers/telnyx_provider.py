"""Telnyx VoIP / PSTN Provider implementation.

Provides programmable calling with Telnyx Call Control and TeXML Streaming.
"""
from __future__ import annotations

import logging
from typing import Any
import xml.etree.ElementTree as ET

import httpx

from app.telephony.base import (
    BaseTelephonyProvider,
    CallDirection,
    CallStatus,
    TelephonyCallResult,
    TelephonyCallStatus,
    WebhookEvent,
)

log = logging.getLogger("app.telephony.telnyx")

_STATUS_MAP: dict[str, CallStatus] = {
    "call.initiated": CallStatus.CONNECTING,
    "call.ringing": CallStatus.RINGING,
    "call.answered": CallStatus.CONNECTED,
    "call.hangup": CallStatus.ENDED,
}


class TelnyxProvider(BaseTelephonyProvider):
    provider_name = "telnyx"

    def __init__(self, api_key: str, default_from_number: str = "") -> None:
        self.api_key = api_key.strip()
        self.default_from_number = default_from_number.strip()
        self.base_url = "https://api.telnyx.com/v2"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def create_call(
        self,
        *,
        to: str,
        from_: str,
        webhook_url: str,
        stream_url: str,
        custom_params: dict[str, str] | None = None,
    ) -> TelephonyCallResult:
        caller_id = from_ or self.default_from_number
        if not self.api_key:
            return TelephonyCallResult(
                call_sid=f"telnyx-mock-{hash(to)}",
                status=CallStatus.FAILED,
                direction=CallDirection.OUTBOUND,
                from_number=caller_id,
                to_number=to,
                provider=self.provider_name,
                error_code="CREDENTIALS_MISSING",
                error_message="Telnyx API Key is not configured.",
            )

        payload = {
            "to": to,
            "from": caller_id,
            "connection_id": (custom_params or {}).get("connection_id", ""),
            "webhook_url": webhook_url,
            "stream_url": stream_url,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(
                    f"{self.base_url}/calls",
                    json=payload,
                    headers=self._headers(),
                )
                data = res.json()
                if res.status_code >= 400:
                    errors = data.get("errors", [{}])[0]
                    return TelephonyCallResult(
                        call_sid="",
                        status=CallStatus.FAILED,
                        direction=CallDirection.OUTBOUND,
                        from_number=caller_id,
                        to_number=to,
                        provider=self.provider_name,
                        error_code=errors.get("code", "TELNYX_ERROR"),
                        error_message=errors.get("detail", "Call creation failed"),
                        raw_response=data,
                    )

                call_data = data.get("data", {})
                sid = call_data.get("call_control_id", call_data.get("call_leg_id", ""))
                return TelephonyCallResult(
                    call_sid=sid,
                    status=CallStatus.CONNECTING,
                    direction=CallDirection.OUTBOUND,
                    from_number=caller_id,
                    to_number=to,
                    provider=self.provider_name,
                    raw_response=data,
                )
        except Exception as e:
            log.exception("Telnyx outbound call exception for %s", to)
            return TelephonyCallResult(
                call_sid="",
                status=CallStatus.FAILED,
                direction=CallDirection.OUTBOUND,
                from_number=caller_id,
                to_number=to,
                provider=self.provider_name,
                error_code="NETWORK_ERROR",
                error_message=str(e),
            )

    async def answer_call(self, call_sid: str, custom_params: dict[str, str] | None = None) -> bool:
        if not self.api_key or not call_sid:
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    f"{self.base_url}/calls/{call_sid}/actions/answer",
                    headers=self._headers(),
                )
                return res.status_code in (200, 204)
        except Exception:
            return False

    async def reject_call(self, call_sid: str, reason: str = "busy") -> bool:
        if not self.api_key or not call_sid:
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    f"{self.base_url}/calls/{call_sid}/actions/reject",
                    json={"cause": "USER_BUSY"},
                    headers=self._headers(),
                )
                return res.status_code in (200, 204)
        except Exception:
            return False

    async def end_call(self, call_sid: str) -> bool:
        if not self.api_key or not call_sid:
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    f"{self.base_url}/calls/{call_sid}/actions/hangup",
                    headers=self._headers(),
                )
                return res.status_code in (200, 204)
        except Exception:
            return False

    async def get_call_status(self, call_sid: str) -> TelephonyCallStatus:
        return TelephonyCallStatus(call_sid=call_sid, status=CallStatus.CONNECTED)

    def generate_twiml_stream_response(
        self,
        *,
        call_sid: str,
        stream_url: str,
        custom_params: dict[str, str] | None = None,
    ) -> str:
        """Telnyx TeXML stream response."""
        root = ET.Element("Response")
        connect = ET.SubElement(root, "Connect")
        ET.SubElement(connect, "Stream", {"url": stream_url, "bidirectionalMode": "rtp"})
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")

    def parse_webhook(self, headers: dict[str, str], payload: dict[str, Any]) -> WebhookEvent:
        data = payload.get("data", {})
        ev_type = data.get("event_type", "")
        payload_data = data.get("payload", {})
        call_sid = payload_data.get("call_control_id", "")
        from_num = payload_data.get("from", "")
        to_num = payload_data.get("to", "")
        status = _STATUS_MAP.get(ev_type, CallStatus.CONNECTED)

        return WebhookEvent(
            event_type=ev_type,
            call_sid=call_sid,
            from_number=from_num,
            to_number=to_num,
            status=status,
            raw_data=payload,
        )

    def verify_webhook_signature(
        self,
        url: str,
        params: dict[str, Any],
        signature: str,
    ) -> bool:
        return True
