"""P4 §E1 — production telephony gates (fail-closed at boot, honest at runtime).

Two layers:

- SETTINGS: a production env that selects a carrier lane (twilio/telnyx/
  livekit_sip/asterisk) must bring the FULL secret set AND an HTTPS webhook
  base URL; webhook signature verification can never be disabled; a
  configured LiveKit SFU must be complete with a browser-reachable wss://
  public URL and (if provided) well-formed TURN JSON. Malformed config
  refuses to BOOT — the honest failure is at deploy time, not per-request.
- RUNTIME: the webhook verification engine never fails open in production —
  every one of its dev escape hatches (missing token, missing signature,
  disabled flag) becomes a refusal when ``app_env == "production"``.
"""
from __future__ import annotations

import pytest

from app.config import Settings


def _prod_base() -> dict:
    return {
        "app_env": "production",
        "secret_key": "a" * 32,
        "jwt_secret": "b" * 32,
        "redis_url": "redis://localhost:6379/0",
        "database_url": "postgresql+asyncpg://user:pass@localhost:5432/dbname",
    }


def _prod_twilio() -> dict:
    return {
        **_prod_base(),
        "telephony_provider": "twilio",
        "twilio_account_sid": "AC123",
        "twilio_auth_token": "tok" + "x" * 29,
        "twilio_phone_number": "+15551234567",
        "telephony_webhook_base_url": "https://api.example.com",
    }


# --------------------------------------------------------------------------- #
# settings gates
# --------------------------------------------------------------------------- #


def test_prod_never_allows_disabled_webhook_verification():
    with pytest.raises(ValueError, match="telephony_verify_webhook_signatures"):
        Settings(**_prod_base(), telephony_verify_webhook_signatures=False)


def test_prod_auto_provider_rejected_when_carrier_creds_present():
    """'auto' silently resolves at runtime; an operator with carrier creds
    must name the lane so the production lane gates actually apply."""
    with pytest.raises(ValueError, match="explicit 'telephony_provider'"):
        Settings(**_prod_base(), twilio_account_sid="AC123")
    with pytest.raises(ValueError, match="explicit 'telephony_provider'"):
        Settings(**_prod_base(), telnyx_api_key="telnyx-key")


def test_prod_auto_provider_without_creds_stays_bootable():
    s = Settings(**_prod_base())
    assert s.telephony_provider == "auto"


def test_prod_twilio_requires_full_secret_set():
    base = {**_prod_base(), "telephony_provider": "twilio",
            "twilio_account_sid": "AC123",
            "telephony_webhook_base_url": "https://api.example.com"}
    with pytest.raises(ValueError, match="TWILIO_AUTH_TOKEN"):
        Settings(**base)


def test_prod_carrier_lane_requires_https_webhook_base_url():
    with pytest.raises(ValueError, match="HTTPS"):
        Settings(**{**_prod_twilio(), "telephony_webhook_base_url": "http://api.example.com"})
    with pytest.raises(ValueError, match="HTTPS"):
        Settings(**{**_prod_twilio(), "telephony_webhook_base_url": ""})


def test_prod_telnyx_requires_api_key():
    with pytest.raises(ValueError, match="TELNYX_API_KEY"):
        Settings(**_prod_base(), telephony_provider="telnyx",
                 telephony_webhook_base_url="https://api.example.com")


def test_prod_livekit_sip_requires_full_sfu_config():
    with pytest.raises(ValueError, match="livekit_sip"):
        Settings(**_prod_base(), telephony_provider="livekit_sip",
                 telephony_webhook_base_url="https://api.example.com",
                 livekit_enabled=False)


def test_prod_asterisk_lane_requires_explicit_admission():
    with pytest.raises(ValueError, match="asterisk"):
        Settings(**_prod_base(), telephony_provider="asterisk")


def test_prod_livekit_must_be_complete_and_tls_public():
    with pytest.raises(ValueError, match="LIVEKIT_URL"):
        Settings(**_prod_base(), livekit_enabled=True, livekit_url="",
                 livekit_api_key="k", livekit_api_secret="s")
    with pytest.raises(ValueError, match="wss://"):
        Settings(**_prod_base(), livekit_enabled=True,
                 livekit_url="wss://internal:7880",
                 livekit_api_key="k", livekit_api_secret="s",
                 livekit_public_url="lk.example.com")


def test_prod_rejects_malformed_turn_ice_json():
    with pytest.raises(ValueError, match="webrtc_ice_servers_json"):
        Settings(**_prod_base(), livekit_enabled=True,
                 livekit_url="wss://sfu", livekit_api_key="k",
                 livekit_api_secret="s", livekit_public_url="wss://pub",
                 webrtc_ice_servers_json="not-json")
    with pytest.raises(ValueError, match="webrtc_ice_servers_json"):
        Settings(**_prod_base(), livekit_enabled=True,
                 livekit_url="wss://sfu", livekit_api_key="k",
                 livekit_api_secret="s", livekit_public_url="wss://pub",
                 webrtc_ice_servers_json='[{"no_urls": true}]')


def test_prod_wellformed_turn_ice_json_passes():
    s = Settings(**_prod_base(), livekit_enabled=True,
                 livekit_url="wss://internal:7880", livekit_api_key="k",
                 livekit_api_secret="s", livekit_public_url="wss://pub.example.com",
                 webrtc_ice_servers_json=(
                     '[{"urls":"turn:turn.example.com:3478?transport=udp",'
                     '"username":"tk","credential":"pw"}]'))
    assert s.is_production is True


def test_prod_full_twilio_lane_boot_clean():
    s = Settings(**_prod_twilio())
    assert s.telephony_provider == "twilio"
    assert s.telephony_verify_webhook_signatures is True


def test_prod_simulated_lane_stays_bootable_without_carrier_secrets():
    s = Settings(**_prod_base(), telephony_provider="simulated")
    assert s.is_production is True


# --------------------------------------------------------------------------- #
# runtime fail-closed (no per-request dev passes in production)
# --------------------------------------------------------------------------- #


class _ProdEnvSwap:
    """Forces selected settings values on EVERY module-owned ``settings``
    binding — the cross-suite reload landmine documented in
    ``test_asterisk_ari_adapter``: ``app.config.settings`` AND
    ``app.telephony.security.settings`` may be different objects after any
    earlier suite reloaded app.config, so values are captured and forced on
    each binding separately, and the flag is ALWAYS forced explicitly
    (never inherited from whatever a previous test left behind)."""

    _MODULES = ("app.config", "app.telephony.security")

    _BASE = (("app_env", "production"),
             ("twilio_auth_token", ""),
             ("telephony_verify_webhook_signatures", True))

    def __init__(self, **overrides: object) -> None:
        import importlib
        self._fields: dict[str, object] = dict(self._BASE)
        self._fields.update(overrides)
        self._targets: list[dict[str, object]] = []
        for path in self._MODULES:
            module = importlib.import_module(path)
            settings = getattr(module, "settings")
            saved: dict[str, object] = {"target": settings}
            for name in self._fields:
                saved[name] = getattr(settings, name)
            self._targets.append(saved)

    def __enter__(self) -> "_ProdEnvSwap":
        for saved in self._targets:
            settings = saved["target"]
            for name, value in self._fields.items():
                setattr(settings, name, value)
        return self

    def __exit__(self, *exc: object) -> None:
        for saved in self._targets:
            settings = saved["target"]
            for name in self._fields:
                setattr(settings, name, saved[name])


def _verify(headers: dict, payload: dict | None = None):
    from app.telephony.security import TelephonySecurity

    return TelephonySecurity.verify_webhook_request(
        headers, payload or {"CallSid": "CA1"}, "https://api.example.com/webhooks/voice")


def test_prod_unsigned_carrier_callback_is_refused():
    with _ProdEnvSwap():
        ok, reason = _verify({})
    assert ok is False
    assert reason == "missing_carrier_signature"


def test_prod_twilio_signature_without_token_is_refused_not_faked():
    with _ProdEnvSwap():
        ok, reason = _verify({"X-Twilio-Signature": "b43=="})
    assert ok is False
    assert reason == "twilio_verification_unconfigured"


def test_prod_disabled_verification_flag_is_second_layer_of_refusal():
    """In production a disabled flag is a refusal: the dev escape ceases to
    exist. Production env AND the disabled flag are forced on every binding,
    so this stays independent of whatever any earlier test left behind."""
    with _ProdEnvSwap(telephony_verify_webhook_signatures=False):
        ok, reason = _verify({})
    assert ok is False
    assert reason == "verification_disabled_in_production"


def test_dev_lanes_keep_their_escape_hatches():
    with _ProdEnvSwap(app_env="development"):
        ok_dev, reason_dev = _verify({})
    assert ok_dev is True
    assert reason_dev == "unauthenticated_dev_pass"
