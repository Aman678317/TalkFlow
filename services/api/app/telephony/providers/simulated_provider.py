"""Simulated / Sandbox Telephony Provider for Local Dev & Testing.

Provides real call state machine progression (initiating -> ringing -> connected -> ended)
without requiring live third-party carrier credentials or incurring PSTN carrier charges.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any
import xml.etree.ElementTree as ET

from app.telephony.base import (
    BaseTelephonyProvider,
    CallDirection,
    CallStatus,
    TelephonyCallResult,
    TelephonyCallStatus,
    WebhookEvent,
)

log = logging.getLogger("app.telephony.simulated")


class SimulatedProvider(BaseTelephonyProvider):
    provider_name = "simulated"

    def __init__(self, default_from_number: str = "+12025550199") -> None:
        self.default_from_number = default_from_number
        self._active_calls: dict[str, dict[str, Any]] = {}

    async def create_call(
        self,
        *,
        to: str,
        from_: str,
        webhook_url: str,
        stream_url: str,
        custom_params: dict[str, str] | None = None,
    ) -> TelephonyCallResult:
        sid = f"SIM_{uuid.uuid4().hex[:16]}"
        caller_id = from_ or self.default_from_number

        self._active_calls[sid] = {
            "sid": sid,
            "to": to,
            "from": caller_id,
            "status": CallStatus.RINGING,
            "stream_url": stream_url,
            "custom_params": custom_params or {},
        }

        # Background simulator: transition from RINGING to CONNECTED after 2s
        asyncio.create_task(self._simulate_progress(sid))

        log.info("Simulated outbound PSTN call placed to %s (sid: %s)", to, sid)
        return TelephonyCallResult(
            call_sid=sid,
            status=CallStatus.RINGING,
            direction=CallDirection.OUTBOUND,
            from_number=caller_id,
            to_number=to,
            provider=self.provider_name,
            raw_response={"simulated": True, "call_sid": sid},
        )

    async def _simulate_progress(self, sid: str) -> None:
        await asyncio.sleep(1.5)
        if sid in self._active_calls:
            self._active_calls[sid]["status"] = CallStatus.CONNECTED

    async def answer_call(self, call_sid: str, custom_params: dict[str, str] | None = None) -> bool:
        if call_sid in self._active_calls:
            self._active_calls[call_sid]["status"] = CallStatus.CONNECTED
            return True
        return True

    async def reject_call(self, call_sid: str, reason: str = "busy") -> bool:
        if call_sid in self._active_calls:
            self._active_calls[call_sid]["status"] = CallStatus.DECLINED
        return True

    async def end_call(self, call_sid: str) -> bool:
        if call_sid in self._active_calls:
            self._active_calls[call_sid]["status"] = CallStatus.ENDED
            return True
        return True

    async def get_call_status(self, call_sid: str) -> TelephonyCallStatus:
        call = self._active_calls.get(call_sid)
        if call:
            return TelephonyCallStatus(call_sid=call_sid, status=call["status"])
        return TelephonyCallStatus(call_sid=call_sid, status=CallStatus.ENDED)

    def generate_twiml_stream_response(
        self,
        *,
        call_sid: str,
        stream_url: str,
        custom_params: dict[str, str] | None = None,
    ) -> str:
        root = ET.Element("Response")
        connect = ET.SubElement(root, "Connect")
        stream = ET.SubElement(connect, "Stream", {"url": stream_url})
        params = custom_params or {}
        params["callSid"] = call_sid
        for k, v in params.items():
            ET.SubElement(stream, "Parameter", {"name": str(k), "value": str(v)})
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")

    def parse_webhook(self, headers: dict[str, str], payload: dict[str, Any]) -> WebhookEvent:
        call_sid = payload.get("call_sid", payload.get("CallSid", "SIM_UNKNOWN"))
        return WebhookEvent(
            event_type="call_status",
            call_sid=call_sid,
            from_number=payload.get("from", self.default_from_number),
            to_number=payload.get("to", ""),
            status=CallStatus.CONNECTED,
            raw_data=payload,
        )

    def verify_webhook_signature(
        self,
        url: str,
        params: dict[str, Any],
        signature: str,
    ) -> bool:
        return True
