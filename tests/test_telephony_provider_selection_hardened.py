"""A carrier lane must never be silently replaced by the simulator.

Evidence behind this suite (2026-10-22, the day-2 ownership map, finding
C-2):

``app/telephony/service.py::get_provider`` resolved the lane like this:

* an explicit ``telephony_provider=twilio`` without credentials fell back to
  the SIMULATED provider outside production (a warning, but a substitution
  nonetheless);
* an ``auto`` lane with a HALF-SET credential set (for example only
  ``TWILIO_ACCOUNT_SID``) picked the simulator with no word at all — so a
  half-configured deployment "placed calls" that went nowhere, and the log
  looked like a working lane.

The Asterisk lane already refused that substitution ("never silently
substituted: a real local call must not become simulated without an explicit
operator choice"); the carrier lanes now behave the same way.

Pinned here: an explicit carrier without credentials fails loudly, a
half-set credential set fails loudly, and only an explicit
``simulated`` (or a completely unconfigured lane) reaches the simulator.
"""
from __future__ import annotations

import pytest

from app.config import settings
from app.errors import ProviderError
from app.telephony.service import TelephonyService


@pytest.fixture()
def service() -> TelephonyService:
    return TelephonyService()


def _force(monkeypatch, **values) -> None:
    for key, value in values.items():
        monkeypatch.setattr(settings, key, value)


def test_an_explicit_carrier_without_credentials_fails_loudly(service, monkeypatch):
    _force(monkeypatch, telephony_provider="twilio",
           twilio_account_sid="", twilio_auth_token="", telnyx_api_key="")
    with pytest.raises(ProviderError) as exc:
        service.get_provider()
    assert "never silently substituted" in str(exc.value).lower()


def test_an_explicit_telnyx_without_credentials_fails_loudly(service, monkeypatch):
    _force(monkeypatch, telephony_provider="telnyx",
           twilio_account_sid="", twilio_auth_token="", telnyx_api_key="")
    with pytest.raises(ProviderError):
        service.get_provider()


def test_a_half_set_credential_set_fails_loudly(service, monkeypatch):
    """The auto lane with only the account SID set."""
    _force(monkeypatch, telephony_provider="auto",
           twilio_account_sid="AC123", twilio_auth_token="", telnyx_api_key="")
    with pytest.raises(ProviderError) as exc:
        service.get_provider()
    assert "partially configured" in str(exc.value).lower()


def test_the_simulated_lane_is_reachable_when_asked_for(service, monkeypatch):
    _force(monkeypatch, telephony_provider="simulated",
           twilio_account_sid="", twilio_auth_token="", telnyx_api_key="")
    provider = service.get_provider()
    assert "simulated" in type(provider).__name__.lower()


def test_an_unconfigured_auto_lane_still_reaches_the_simulator(service, monkeypatch):
    """No carrier credentials at all is a legitimate 'no carrier configured'."""
    _force(monkeypatch, telephony_provider="auto",
           twilio_account_sid="", twilio_auth_token="", telnyx_api_key="")
    provider = service.get_provider()
    assert "simulated" in type(provider).__name__.lower()


def test_a_complete_credential_set_still_selects_the_carrier(service, monkeypatch):
    _force(monkeypatch, telephony_provider="auto",
           twilio_account_sid="AC123", twilio_auth_token="token", telnyx_api_key="")
    provider = service.get_provider()
    assert "twilio" in type(provider).__name__.lower()
