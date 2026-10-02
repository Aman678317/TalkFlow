"""Twilio PSTN Provider implementation.

Provides programmable outbound/inbound phone calls with bidirectional
WebSocket Media Streams and standard TwiML audio stream negotiation.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
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

log = logging.getLogger("app.telephony.twilio")

_STATUS_MAP: dict[str, CallStatus] = {
    "queued": CallStatus.INITIATING,
    "initiated": CallStatus.CONNECTING,
    "ringing": CallStatus.RINGING,
    "in-progress": CallStatus.CONNECTED,
    "completed": CallStatus.ENDED,
    "busy": CallStatus.BUSY,
    "no-answer": CallStatus.NO_ANSWER,
    "canceled": CallStatus.DECLINED,
    "failed": CallStatus.FAILED,
}


class TwilioProvider(BaseTelephonyProvider):
    provider_name = "twilio"

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        default_from_number: str = "",
    ) -> None:
        self.account_sid = account_sid.strip()
        self.auth_token = auth_token.strip()
        self.default_from_number = default_from_number.strip()
        self.base_url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}"

    def _auth(self) -> tuple[str, str]:
        return (self.account_sid, self.auth_token)

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
        if not self.account_sid or not self.auth_token:
            return TelephonyCallResult(
                call_sid=f"mock-{hash(to)}",
                status=CallStatus.FAILED,
                direction=CallDirection.OUTBOUND,
                from_number=caller_id,
                to_number=to,
                provider=self.provider_name,
                error_code="CREDENTIALS_MISSING",
                error_message="Twilio Account SID or Auth Token is not configured.",
            )

        payload: dict[str, Any] = {
            "To": to,
            "From": caller_id,
        }
        # Twilio cloud servers cannot fetch 'http://localhost' or 'http://127.0.0.1' URLs.
        # If running locally without a public ngrok webhook URL, supply inline TwiML directly:
        is_public_url = bool(
            webhook_url and not any(loc in webhook_url for loc in ["localhost", "127.0.0.1", "0.0.0.0"])
        )
        if is_public_url:
            payload["Url"] = webhook_url
            payload["StatusCallback"] = f"{webhook_url}/status"
            payload["StatusCallbackEvent"] = ["initiated", "ringing", "answered", "completed"]
            payload["StatusCallbackMethod"] = "POST"
        else:
            # Inline TwiML instruction directly embedded in Twilio REST call:
            say_text = "Welcome to GlobalTalk AI. Your real-time translated voice session is now connected."
            payload["Twiml"] = f'<Response><Say voice="Polly.Aditi">{say_text}</Say><Pause length="60"/></Response>'

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(
                    f"{self.base_url}/Calls.json",
                    data=payload,
                    auth=self._auth(),
                )
                data = res.json()
                if res.status_code >= 400:
                    err_msg = data.get("message", f"Twilio HTTP {res.status_code}")
                    code = str(data.get("code", "TWILIO_ERROR"))
                    log.error("Twilio call failed: %s (code %s)", err_msg, code)
                    return TelephonyCallResult(
                        call_sid=data.get("sid", ""),
                        status=CallStatus.FAILED,
                        direction=CallDirection.OUTBOUND,
                        from_number=caller_id,
                        to_number=to,
                        provider=self.provider_name,
                        error_code=code,
                        error_message=err_msg,
                        raw_response=data,
                    )

                sid = data.get("sid", "")
                tw_status = data.get("status", "queued")
                mapped_status = _STATUS_MAP.get(tw_status, CallStatus.CONNECTING)
                return TelephonyCallResult(
                    call_sid=sid,
                    status=mapped_status,
                    direction=CallDirection.OUTBOUND,
                    from_number=caller_id,
                    to_number=to,
                    provider=self.provider_name,
                    raw_response=data,
                )
        except Exception as e:
            log.exception("Exception placing Twilio outbound call to %s", to)
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
        # In Twilio Programmable Voice, answering is handled by responding with TwiML
        return True

    async def reject_call(self, call_sid: str, reason: str = "busy") -> bool:
        return await self.end_call(call_sid)

    async def end_call(self, call_sid: str) -> bool:
        if not self.account_sid or not self.auth_token or not call_sid:
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    f"{self.base_url}/Calls/{call_sid}.json",
                    data={"Status": "completed"},
                    auth=self._auth(),
                )
                return res.status_code in (200, 204)
        except Exception as e:
            log.warning("Failed to end Twilio call %s: %s", call_sid, e)
            return False

    async def get_call_status(self, call_sid: str) -> TelephonyCallStatus:
        if not self.account_sid or not self.auth_token or not call_sid:
            return TelephonyCallStatus(call_sid=call_sid, status=CallStatus.ENDED)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(
                    f"{self.base_url}/Calls/{call_sid}.json",
                    auth=self._auth(),
                )
                if res.status_code == 200:
                    data = res.json()
                    status = _STATUS_MAP.get(data.get("status", ""), CallStatus.ENDED)
                    dur = int(data.get("duration") or 0)
                    price = int(float(data.get("price") or 0.0) * -100) if data.get("price") else 0
                    return TelephonyCallStatus(
                        call_sid=call_sid,
                        status=status,
                        duration_seconds=dur,
                        price_cents=price,
                    )
        except Exception:
            pass
        return TelephonyCallStatus(call_sid=call_sid, status=CallStatus.ENDED)

    def generate_twiml_stream_response(
        self,
        *,
        call_sid: str,
        stream_url: str,
        custom_params: dict[str, str] | None = None,
    ) -> str:
        """Generate carrier TwiML with bidirectional <Connect><Stream>."""
        root = ET.Element("Response")
        connect = ET.SubElement(root, "Connect")
        stream = ET.SubElement(connect, "Stream", {"url": stream_url})

        params = custom_params or {}
        params["callSid"] = call_sid
        for k, v in params.items():
            ET.SubElement(stream, "Parameter", {"name": str(k), "value": str(v)})

        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")

    def parse_webhook(self, headers: dict[str, str], payload: dict[str, Any]) -> WebhookEvent:
        call_sid = payload.get("CallSid", payload.get("call_sid", ""))
        from_num = payload.get("From", payload.get("from", ""))
        to_num = payload.get("To", payload.get("to", ""))
        call_status_str = payload.get("CallStatus", payload.get("status", "in-progress"))
        mapped_status = _STATUS_MAP.get(call_status_str.lower(), CallStatus.CONNECTED)

        digits = payload.get("Digits")
        stream_sid = payload.get("StreamSid")

        return WebhookEvent(
            event_type="call_status",
            call_sid=call_sid,
            from_number=from_num,
            to_number=to_num,
            status=mapped_status,
            digits=digits,
            stream_sid=stream_sid,
            raw_data=payload,
        )

    def verify_webhook_signature(
        self,
        url: str,
        params: dict[str, Any],
        signature: str,
    ) -> bool:
        """Verify X-Twilio-Signature against AuthToken."""
        if not self.auth_token or not signature:
            return True  # Bypass in dev/test mode when unset
        data = url + "".join(f"{k}{params[k]}" for k in sorted(params.keys()))
        computed = base64.b64encode(
            hmac.new(self.auth_token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1).digest()
        ).decode("utf-8")
        return hmac.compare_digest(computed, signature)
