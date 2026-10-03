"""Telephony Service & Provider Registry."""
from __future__ import annotations

import logging
from typing import ClassVar

from app.config import settings
from app.errors import ProviderError
from app.telephony.base import BaseTelephonyProvider
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

    def get_provider(self, provider_name: str | None = None) -> BaseTelephonyProvider:
        """Resolve the active telephony provider."""
        req_name = (provider_name or settings.telephony_provider).lower()

        if req_name == "twilio":
            if settings.twilio_account_sid and settings.twilio_auth_token:
                return self._providers["twilio"]
            if settings.is_production:
                raise ProviderError("Twilio telephony requested in production but TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN are missing")
            log.warning("Twilio credentials not configured; falling back to simulated provider")
            return self._providers["simulated"]

        if req_name == "telnyx":
            if settings.telnyx_api_key:
                return self._providers["telnyx"]
            if settings.is_production:
                raise ProviderError("Telnyx telephony requested in production but TELNYX_API_KEY is missing")
            log.warning("Telnyx credentials not configured; falling back to simulated provider")
            return self._providers["simulated"]

        if req_name == "simulated":
            return self._providers["simulated"]

        # auto mode: choose first provider that has credentials, or simulated
        if settings.twilio_account_sid and settings.twilio_auth_token:
            return self._providers["twilio"]
        if settings.telnyx_api_key:
            return self._providers["telnyx"]

        return self._providers["simulated"]


_telephony_service: TelephonyService | None = None


def get_telephony_service() -> TelephonyService:
    global _telephony_service
    if _telephony_service is None:
        _telephony_service = TelephonyService()
    return _telephony_service
