"""Telephony Service & Provider Registry."""
from __future__ import annotations

import logging
from typing import ClassVar

from app.config import settings
from app.errors import ProviderError
from app.telephony.base import BaseTelephonyProvider
from app.telephony.providers.asterisk_provider import AsteriskARIProvider
from app.telephony.providers.simulated_provider import SimulatedProvider
from app.telephony.providers.telnyx_provider import TelnyxProvider
from app.telephony.providers.twilio_provider import TwilioProvider

log = logging.getLogger("app.telephony.service")


class TelephonyService:
    _instance: ClassVar[TelephonyService | None] = None

    def __init__(self) -> None:
        self._providers: dict[str, BaseTelephonyProvider] = {}
        self._init_providers()

    def _init_providers(self) -> None:
        # 1. Twilio
        self._providers["twilio"] = TwilioProvider(
            account_sid=settings.twilio_account_sid,
            auth_token=settings.twilio_auth_token,
            default_from_number=settings.twilio_phone_number,
        )

        # 2. Telnyx
        self._providers["telnyx"] = TelnyxProvider(
            api_key=settings.telnyx_api_key,
            default_from_number=settings.telnyx_phone_number,
        )

        # 3. Simulated
        self._providers["simulated"] = SimulatedProvider(
            default_from_number=settings.twilio_phone_number or "+12025550199",
        )

        # 4. Asterisk local SIP (P1 adapter design): construction is cheap (no
        # network), but selection is gated below — a disabled flag or missing
        # config fails loudly instead of silently falling back, and auto mode
        # never selects Asterisk. See docs/ASTERISK_LOCAL_SIP_LAB.md.
        self._providers["asterisk"] = AsteriskARIProvider.from_settings()

    def get_provider(self, provider_name: str | None = None) -> BaseTelephonyProvider:
        """Resolve the active telephony provider.

        A carrier lane is never silently substituted (issue #109 class 3,
        day-2 finding C-2): the old code answered an explicit
        ``telephony_provider=twilio`` without credentials with the SIMULATED
        provider outside production, and an ``auto`` lane with a half-set
        credential set picked the simulator with no word at all — so a
        half-configured deployment "made calls" that went nowhere, and the
        log looked like a working lane. The Asterisk lane already refused
        that substitution; the carrier lanes now behave the same way.
        """
        req_name = (provider_name or settings.telephony_provider).lower()

        if req_name == "twilio":
            if settings.twilio_account_sid and settings.twilio_auth_token:
                return self._providers["twilio"]
            raise ProviderError(
                "Twilio telephony requested but TWILIO_ACCOUNT_SID / "
                "TWILIO_AUTH_TOKEN are missing. Never silently substituted: a "
                "real call must not become simulated without an explicit "
                "operator choice (set telephony_provider=simulated for the "
                "simulated lane)."
            )

        if req_name == "telnyx":
            if settings.telnyx_api_key:
                return self._providers["telnyx"]
            raise ProviderError(
                "Telnyx telephony requested but TELNYX_API_KEY is missing. "
                "Never silently substituted: a real call must not become "
                "simulated without an explicit operator choice (set "
                "telephony_provider=simulated for the simulated lane)."
            )

        if req_name == "simulated":
            return self._providers["simulated"]

        if req_name == "asterisk":
            asterisk = self._providers.get("asterisk")
            if settings.asterisk_telephony_enabled and asterisk is not None and asterisk.is_ready():
                return asterisk
            raise ProviderError(
                "Asterisk telephony requested while disabled or not configured "
                "(requires ASTERISK_TELEPHONY_ENABLED=true, ARI base URL/credentials "
                "and a non-empty ASTERISK_ALLOWED_EXTENSIONS). Never silently "
                "substituted: a real local call must not become simulated without "
                "an explicit operator choice."
            )

        # auto mode: choose the first provider that has a COMPLETE credential
        # set, or the simulated lane when no carrier is configured at all.
        # A half-set credential set is a configuration error, not a reason to
        # simulate.
        if settings.twilio_account_sid or settings.twilio_auth_token:
            if settings.twilio_account_sid and settings.twilio_auth_token:
                return self._providers["twilio"]
            raise ProviderError(
                "Telephony is set to 'auto' and TWILIO credentials are only "
                "partially configured (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN "
                "must both be set). Never silently substituted: a real call must "
                "not become simulated without an explicit operator choice."
            )
        if settings.telnyx_api_key:
            return self._providers["telnyx"]

        return self._providers["simulated"]

    def get_registered_provider(self, provider_name: str) -> BaseTelephonyProvider | None:
        """Access a constructed provider without eligibility gating (wiring use)."""
        return self._providers.get(provider_name.lower())


_telephony_service: TelephonyService | None = None


def get_telephony_service() -> TelephonyService:
    global _telephony_service
    if _telephony_service is None:
        _telephony_service = TelephonyService()
    return _telephony_service
