"""Asterisk (local SIP) telephony provider adapter.

Implements the P1 adapter design in ``docs/ASTERISK_LOCAL_SIP_LAB.md``:

- **ARI REST is the control plane.** The authenticated ARI WebSocket is the
  event path (see ``ari_events``). There are deliberately NO HTTP webhooks for
  this provider: ``parse_webhook`` raises so it can never be spoofed through
  the carrier webhook endpoint, and ``verify_webhook_signature`` always
  fails closed.
- **Destinations are local SIP extensions only**, enforced against the
  operator-configured allowlist BEFORE any ARI action. Public/E.164 dialing
  is rejected here unless a separate trunk feature is explicitly authorized.
- **Correlation:** the originate POST uses a client-chosen channel ID
  (``talkflow-<call uuid>``), so the provider reference equals the correlation
  ID. A timeout after originate is an UNKNOWN outcome: the provider
  reconciles by GETting that channel (never blind-retries, which could
  duplicate a very real local call).
- **Scope:** signaling only. Media translation / ExternalMedia and inbound
  (Stasis→provider) routing are pre-implementation decisions parked by the
  design doc and are NOT claimed here.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from app.errors import ProviderError, ValidationError
from app.telephony.ari_client import (
    ARIConfig,
    ARIClient,
    ARINotFound,
    ARIRequestFailed,
    ARIUnavailable,
    ARITimeout,
    CHANNEL_ID_PREFIX,
)
from app.telephony.base import (
    BaseTelephonyProvider,
    CallDirection,
    CallStatus,
    TelephonyCallResult,
    TelephonyCallStatus,
    WebhookEvent,
)

log = logging.getLogger("app.telephony.asterisk")

# ARI channel JSON ``state`` values for PJSIP channels.
_ARI_STATE_MAP: dict[str, CallStatus] = {
    "down": CallStatus.CONNECTING,
    "ringing": CallStatus.RINGING,
    "up": CallStatus.CONNECTED,
}

_ARI_CORRELATION_VARIABLE = "TALKFLOW_CALL_ID"


class AsteriskARIProvider(BaseTelephonyProvider):
    provider_name = "asterisk"

    def __init__(
        self,
        ari: ARIClient,
        allowlist: list[str],
        *,
        default_caller_id: str = "",
    ) -> None:
        self.ari = ari
        # Operator-controlled allowlist; entries are exact after whitespace trim.
        self._allowlist = [ext.strip() for ext in allowlist if str(ext).strip()]
        self._default_caller_id = default_caller_id
        # channel_id → call_sid. Shared with the ARI event consumer (main.py
        # wiring); today call_sid == channel_id (deterministic originate), the
        # map stays the one place to extend for future multi-leg dialouts.
        self.channel_map: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # configuration
    # ------------------------------------------------------------------ #
    @classmethod
    def from_settings(cls) -> "AsteriskARIProvider":
        from app.config import settings

        allowlist = [
            ext.strip()
            for ext in settings.asterisk_allowed_extensions.split(",")
            if ext.strip()
        ]
        return cls(
            ARIClient(ARIConfig.from_settings()),
            allowlist,
            default_caller_id=settings.telephony_human_mobile_number
            or settings.twilio_phone_number,
        )

    def is_ready(self) -> bool:
        """True when explicit operator configuration completed AND an allowlist exists."""
        return self.ari.config.is_configured() and bool(self._allowlist)

    # ------------------------------------------------------------------ #
    # destination policy
    # ------------------------------------------------------------------ #
    def normalize_destination(self, to: str) -> str:
        """Validate & return the allowlisted extension, or raise ``ValidationError``."""
        dest = str(to or "").strip()
        if not dest:
            raise ValidationError("Destination is required for an Asterisk call.")
        if dest not in self._allowlist:
            raise ValidationError(
                "Destination is not in the configured Asterisk extension allowlist "
                f"(allowed: {', '.join(self._allowlist) or '<empty>'}). Public/E.164 "
                "dialing is not available on this provider — do not dial PSTN numbers."
            )
        return dest

    # ------------------------------------------------------------------ #
    # outbound origination
    # ------------------------------------------------------------------ #
    async def create_call(
        self,
        *,
        to: str,
        from_: str,
        webhook_url: str,
        stream_url: str,
        custom_params: dict[str, str] | None = None,
    ) -> TelephonyCallResult:
        params = dict(custom_params or {})
        try:
            dest = self.normalize_destination(to)
        except ValidationError as exc:
            return self._failed_result(
                to, from_,
                status=CallStatus.INVALID_NUMBER,
                error_code="DESTINATION_NOT_IN_ALLOWLIST",
                message=str(exc),
            )

        if not self.ari.config.is_configured():
            return self._failed_result(
                dest, from_,
                status=CallStatus.FAILED,
                error_code="ARI_NOT_CONFIGURED",
                message="Asterisk ARI base URL / credentials are not configured.",
            )

        call_id = params.get("call_id") or uuid.uuid4().hex
        channel_id = f"{CHANNEL_ID_PREFIX}{call_id}"
        log.info(
            "Asterisk originate: %s -> PJSIP/%s (channel %s, app %s)",
            from_ or self._default_caller_id,
            dest,
            channel_id,
            self.ari.config.app_name,
        )

        try:
            await self.ari.create_channel(
                channel_id=channel_id,
                endpoint=f"PJSIP/{dest}",
                app=self.ari.config.app_name,
                app_args=[call_id],
                variables={
                    _ARI_CORRELATION_VARIABLE: call_id,
                    "TALKFLOW_DESTINATION": dest,
                },
            )
        except ARITimeout:
            # Unknown outcome — the create may have taken effect server-side.
            # Reconcile via the deterministic channel ID; NEVER blind-retry.
            return await self._reconcile_after_create_timeout(
                channel_id, dest, from_, call_id
            )
        except ARIUnavailable as exc:
            return self._failed_result(
                dest, from_,
                status=CallStatus.FAILED,
                error_code="ARI_UNAVAILABLE",
                message=f"Asterisk ARI is unreachable — provider unavailable: {exc}",
            )
        except ARIRequestFailed as exc:
            return self._failed_result(
                dest, from_,
                status=CallStatus.FAILED,
                error_code="ARI_REQUEST_REJECTED",
                message=str(exc),
            )

        self.channel_map[channel_id] = channel_id
        return await self._dial(channel_id, dest, from_)

    async def _dial(
        self, channel_id: str, dest: str, from_: str
    ) -> TelephonyCallResult:
        """Start dialing a channel already in the Stasis app (bounded, no loops)."""
        try:
            await self.ari.dial(channel_id)
        except ARITimeout:
            # Dial outcome unknown; the ask is not "did the request land?" but
            # "what does the channel look like now?". One bounded reconcile +
            # a single re-dial is allowed ONLY when the channel is provably
            # still Down (meaning dial never fired).
            return await self._recover_dial_timeout(channel_id, dest, from_)
        except ARIUnavailable as exc:
            return self._failed_result(
                dest, from_,
                status=CallStatus.FAILED,
                error_code="ARI_UNAVAILABLE",
                message=f"Channel created but dial dispatch failed: {exc}",
            )
        except ARIRequestFailed as exc:
            return self._failed_result(
                dest, from_,
                status=CallStatus.FAILED,
                error_code="DIAL_REJECTED",
                message=str(exc),
            )

        return TelephonyCallResult(
            call_sid=channel_id,
            status=CallStatus.CONNECTING,
            direction=CallDirection.OUTBOUND,
            from_number=from_ or self._default_caller_id,
            to_number=dest,
            provider=self.provider_name,
            raw_response={"channel": channel_id, "endpoint": f"PJSIP/{dest}"},
        )

    async def _reconcile_after_create_timeout(
        self, channel_id: str, dest: str, from_: str, call_id: str
    ) -> TelephonyCallResult:
        try:
            chan = await self.ari.get_channel(channel_id)
        except ARINotFound:
            return self._failed_result(
                dest, from_,
                status=CallStatus.FAILED,
                error_code="ARI_TIMEOUT_UNKNOWN",
                message=(
                    "Originate timed out and reconcile found no channel for "
                    f"{channel_id}; outcome unknown, no retry issued."
                ),
            )
        except ARITimeout as exc:
            return self._failed_result(
                dest, from_,
                status=CallStatus.FAILED,
                error_code="ARI_UNAVAILABLE",
                message=f"Reconcile lookup also timed out — outcome unverified: {exc}",
            )
        except ARIUnavailable as exc:
            return self._failed_result(
                dest, from_,
                status=CallStatus.FAILED,
                error_code="ARI_UNAVAILABLE",
                message=f"Reconcile lookup unreachable — outcome unverified: {exc}",
            )

        self.channel_map[channel_id] = channel_id
        state = str(chan.get("state") or "Down")
        if state.lower() == "down":
            # Channel exists but provably never dialed: dial it once now.
            result = await self._dial(channel_id, dest, from_)
            log.info(
                "Originate reconcile for %s: channel existed in Down state — dialed once",
                channel_id,
            )
            return result
        status = _ARI_STATE_MAP.get(state.lower(), CallStatus.CONNECTING)
        log.info("Originate reconcile for %s: found channel in state %s", channel_id, state)
        return TelephonyCallResult(
            call_sid=channel_id,
            status=status,
            direction=CallDirection.OUTBOUND,
            from_number=from_ or self._default_caller_id,
            to_number=dest,
            provider=self.provider_name,
            raw_response={"reconciled_after": "create_timeout", "ari_state": state},
        )

    async def _recover_dial_timeout(
        self, channel_id: str, dest: str, from_: str
    ) -> TelephonyCallResult:
        try:
            chan = await self.ari.get_channel(channel_id)
        except (ARINotFound, ARITimeout, ARIUnavailable) as exc:
            return self._failed_result(
                dest, from_,
                status=CallStatus.FAILED,
                error_code="ARI_UNAVAILABLE",
                message=f"Dial timed out and reconcile failed — outcome unverified: {exc}",
            )
        state = str(chan.get("state") or "Down").lower()
        if state == "down":
            try:
                await self.ari.dial(channel_id)
            except (ARITimeout, ARIUnavailable, ARIRequestFailed) as exc:
                return self._failed_result(
                    dest, from_,
                    status=CallStatus.FAILED,
                    error_code="ARI_UNAVAILABLE",
                    message=f"Bounded re-dial after timeout failed — outcome unverified: {exc}",
                )
            status = CallStatus.CONNECTING
        else:
            status = _ARI_STATE_MAP.get(state, CallStatus.CONNECTING)
        return TelephonyCallResult(
            call_sid=channel_id,
            status=status,
            direction=CallDirection.OUTBOUND,
            from_number=from_ or self._default_caller_id,
            to_number=dest,
            provider=self.provider_name,
            raw_response={"reconciled_after": "dial_timeout", "ari_state": state},
        )

    # ------------------------------------------------------------------ #
    # lifecycle mirroring
    # ------------------------------------------------------------------ #
    async def end_call(self, call_sid: str) -> bool:
        if not call_sid:
            return False
        try:
            await self.ari.hangup(call_sid)
            return True
        except ARINotFound:
            log.info("Asterisk channel %s already gone; end_call treated as success", call_sid)
            return True
        except (ARITimeout, ARIUnavailable, ARIRequestFailed) as exc:
            log.warning("Failed to end Asterisk call %s: %s", call_sid, exc)
            return False

    async def get_call_status(self, call_sid: str) -> TelephonyCallStatus:
        """Poll ARI channel state.

        A missing channel means the call finished (channel destroyed ⇒ ended).
        An unreachable ARI server raises ``ProviderError`` rather than fabricating
        ENDED: reporting a false terminal state would absorb real future events
        in the session state machine.
        """
        if not call_sid:
            return TelephonyCallStatus(call_sid=call_sid, status=CallStatus.ENDED)
        try:
            chan = await self.ari.get_channel(call_sid)
        except ARINotFound:
            return TelephonyCallStatus(
                call_sid=call_sid,
                status=CallStatus.ENDED,
                error_code="CHANNEL_DESTROYED",
                error_message="ARI channel no longer exists.",
            )
        except (ARITimeout, ARIUnavailable, ARIRequestFailed) as exc:
            raise ProviderError(f"Asterisk ARI unavailable: {exc}") from exc
        state = str(chan.get("state") or "Down")
        return TelephonyCallStatus(
            call_sid=call_sid,
            status=_ARI_STATE_MAP.get(state.lower(), CallStatus.CONNECTING),
        )

    # ------------------------------------------------------------------ #
    # inbound / media surface (honest non-support — see module docstring)
    # ------------------------------------------------------------------ #
    async def answer_call(self, call_sid: str, custom_params: dict[str, str] | None = None) -> bool:
        log.warning(
            "answer_call unsupported for provider 'asterisk': inbound Stasis legs "
            "are not routed by this adapter yet (out of documented scope)"
        )
        return False

    async def reject_call(self, call_sid: str, reason: str = "busy") -> bool:
        log.warning(
            "reject_call unsupported for provider 'asterisk' (no inbound path yet)"
        )
        return False

    def generate_twiml_stream_response(
        self,
        *,
        call_sid: str,
        stream_url: str,
        custom_params: dict[str, str] | None = None,
    ) -> str:
        raise ProviderError(
            "TwiML is not applicable to the Asterisk provider: media is bridged by "
            "Asterisk dialplan/ARI, not carrier XML. (ExternalMedia translation is "
            "an explicitly parked design decision.)"
        )

    def parse_webhook(self, headers: dict[str, str], payload: dict[str, Any]) -> WebhookEvent:
        raise ProviderError(
            "Asterisk events arrive over the authenticated ARI WebSocket, not HTTP "
            "webhooks. This provider must never be invoked from the carrier "
            "webhook endpoint."
        )

    def verify_webhook_signature(
        self,
        url: str,
        params: dict[str, Any],
        signature: str,
    ) -> bool:
        # Fail closed: there is no HTTP webhook surface for this provider, so
        # any POST claiming to be one must be rejected.
        return False

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _failed_result(
        self,
        to: str,
        from_: str,
        *,
        status: CallStatus,
        error_code: str,
        message: str,
    ) -> TelephonyCallResult:
        log.warning("Asterisk call to %s failed (%s): %s", to, error_code, message)
        return TelephonyCallResult(
            call_sid=f"{CHANNEL_ID_PREFIX}{uuid.uuid4().hex}",
            status=status,
            direction=CallDirection.OUTBOUND,
            from_number=from_ or self._default_caller_id,
            to_number=to,
            provider=self.provider_name,
            error_code=error_code,
            error_message=message,
        )
