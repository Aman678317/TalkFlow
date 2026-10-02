"""Telephony provider abstraction interfaces & data contracts."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CallDirection(str, Enum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class CallStatus(str, Enum):
    IDLE = "idle"
    INITIATING = "initiating"
    CONNECTING = "connecting"
    RINGING = "ringing"
    CONNECTED = "connected"
    TRANSLATING = "translating"
    ENDING = "ending"
    ENDED = "ended"
    BUSY = "busy"
    DECLINED = "declined"
    NO_ANSWER = "no_answer"
    TIMEOUT = "timeout"
    FAILED = "failed"
    INVALID_NUMBER = "invalid_number"
    UNSUPPORTED_COUNTRY = "unsupported_country"


@dataclass
class TelephonyCallResult:
    call_sid: str
    status: CallStatus
    direction: CallDirection
    from_number: str
    to_number: str
    provider: str
    error_code: str | None = None
    error_message: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)


@dataclass
class TelephonyCallStatus:
    call_sid: str
    status: CallStatus
    duration_seconds: int = 0
    price_cents: int = 0
    currency: str = "USD"
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class WebhookEvent:
    event_type: str  # call_status | incoming_call | media_stream | dtmf
    call_sid: str
    from_number: str
    to_number: str
    status: CallStatus
    digits: str | None = None
    stream_sid: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)


class BaseTelephonyProvider(ABC):
    """Abstract interface that every PSTN/VoIP telephony provider must implement."""

    provider_name: str = "base"

    @abstractmethod
    async def create_call(
        self,
        *,
        to: str,
        from_: str,
        webhook_url: str,
        stream_url: str,
        custom_params: dict[str, str] | None = None,
    ) -> TelephonyCallResult:
        """Place an outbound call via the PSTN network."""
        ...

    @abstractmethod
    async def answer_call(self, call_sid: str, custom_params: dict[str, str] | None = None) -> bool:
        """Answer an incoming PSTN call."""
        ...

    @abstractmethod
    async def reject_call(self, call_sid: str, reason: str = "busy") -> bool:
        """Reject an incoming call with busy or decline signal."""
        ...

    @abstractmethod
    async def end_call(self, call_sid: str) -> bool:
        """Terminate an active call."""
        ...

    @abstractmethod
    async def get_call_status(self, call_sid: str) -> TelephonyCallStatus:
        """Poll latest call status from provider."""
        ...

    @abstractmethod
    def generate_twiml_stream_response(
        self,
        *,
        call_sid: str,
        stream_url: str,
        custom_params: dict[str, str] | None = None,
    ) -> str:
        """Generate carrier XML (e.g. TwiML/TeXML) that connects call to bidirectional media stream."""
        ...

    @abstractmethod
    def parse_webhook(self, headers: dict[str, str], payload: dict[str, Any]) -> WebhookEvent:
        """Parse carrier webhook into unified WebhookEvent."""
        ...

    @abstractmethod
    def verify_webhook_signature(
        self,
        url: str,
        params: dict[str, Any],
        signature: str,
    ) -> bool:
        """Verify provider HMAC signature to protect against webhook spoofing."""
        ...
