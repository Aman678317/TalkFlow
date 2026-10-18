"""P0 telephony gate: carrier webhooks must be signed, and provider status
retries must be idempotent (same callback twice = one transition, one event,
one usage record; late out-of-order callbacks never roll a terminal call
back). The "simulate a real carrier" lane uses the simulated provider, so
every claim here is CI-verifiable without PSTN credentials.

Note: tests patch settings through ``app.telephony.security.settings`` --
the settings instance the verification engine itself reads. Patching an
instance imported via ``from app.config import settings`` can fork from the
module's binding when other tests import telephony modules before the app
fixture reloads app.config, making flag toggles silently ignored.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from urllib.parse import urlencode

import pytest


def _prod_security_posture(monkeypatch):
    """Force the settings instance security.py reads into a production posture."""
    import app.telephony.security as sec

    monkeypatch.setattr(sec.settings, "telephony_verify_webhook_signatures", True)
    monkeypatch.setattr(sec.settings, "twilio_auth_token", "prod-token-value")
    monkeypatch.setattr(sec.settings, "app_env", "production")


# --------------------------------------------------------------------------- #
# Signature verification units
# --------------------------------------------------------------------------- #


def _twilio_signature(auth_token: str, url: str, params: dict) -> str:
    """Compute the exact Twilio X-Twilio-Signature the API expects."""
    s = url
    for key in sorted(params.keys()):
        s += f"{key}{params[key]}"
    digest = hmac.new(
        auth_token.encode("utf-8"), s.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("utf-8")


def test_twilio_valid_signature_accepted():
    from app.telephony.security import TelephonySecurity

    token = "super-secret-twilio-auth-token"
    url = "https://api.example.com/api/v1/telephony/webhooks/status"
    params = {"CallSid": "CA123", "CallStatus": "completed"}
    sig = _twilio_signature(token, url, params)
    assert TelephonySecurity.verify_twilio_signature(url, params, sig, auth_token=token) is True


def test_twilio_tampered_signature_rejected():
    from app.telephony.security import TelephonySecurity

    token = "super-secret-twilio-auth-token"
    url = "https://api.example.com/api/v1/telephony/webhooks/status"
    params = {"CallSid": "CA123", "CallStatus": "completed"}
    good = _twilio_signature(token, url, params)
    bad = ("A" if good[0] != "A" else "B") + good[1:]
    assert TelephonySecurity.verify_twilio_signature(url, params, bad, auth_token=token) is False
    # A signature computed over a DIFFERENT url/params must not validate:
    other = _twilio_signature(token, url, {"CallSid": "CA999", "CallStatus": "completed"})
    assert TelephonySecurity.verify_twilio_signature(url, params, other, auth_token=token) is False


def test_twilio_missing_signature_rejected_when_token_configured(monkeypatch):
    import app.telephony.security as sec

    token = "super-secret-twilio-auth-token"
    monkeypatch.setattr(sec.settings, "twilio_auth_token", token)
    assert sec.TelephonySecurity.verify_twilio_signature(
        "https://x.example.com/w", {}, None) is False


def test_verify_webhook_rejects_unsigned_request_in_production(monkeypatch):
    """Production posture: no carrier header present -> fail closed."""
    import app.telephony.security as sec

    _prod_security_posture(monkeypatch)
    ok, reason = sec.TelephonySecurity.verify_webhook_request(
        {}, {}, "https://api.example.com/w")
    assert ok is False
    assert reason == "missing_carrier_signature"


def test_verify_webhook_rejects_bad_twilio_signature_in_production(monkeypatch):
    import app.telephony.security as sec

    _prod_security_posture(monkeypatch)
    ok, reason = sec.TelephonySecurity.verify_webhook_request(
        {"X-Twilio-Signature": "forged=="}, {}, "https://api.example.com/w")
    assert ok is False
    assert reason == "invalid_twilio_signature"


def test_verify_webhook_twilio_verified_path(monkeypatch):
    import app.telephony.security as sec

    token = "prod-token-value"
    url = "https://api.example.com/api/v1/telephony/webhooks/status"
    params = {"CallSid": "CA1", "CallStatus": "completed"}
    sig = _twilio_signature(token, url, params)
    _prod_security_posture(monkeypatch)
    ok, reason = sec.TelephonySecurity.verify_webhook_request(
        {"X-Twilio-Signature": sig}, params, url)
    assert ok is True
    assert reason == "twilio_verified"


def test_verify_webhook_missing_token_dev_mode_pass(monkeypatch):
    """Without a carrier credential the sandbox must not dead-stop drills."""
    import app.telephony.security as sec

    monkeypatch.setattr(sec.settings, "telephony_verify_webhook_signatures", True)
    monkeypatch.setattr(sec.settings, "twilio_auth_token", "")
    ok, reason = sec.TelephonySecurity.verify_webhook_request(
        {"x-twilio-signature": "anything"}, {}, "https://api.example.com/w")
    assert ok is True
    assert reason == "twilio_dev_mode"


def test_telnyx_expired_timestamp_rejected(monkeypatch):
    import time

    import app.telephony.security as sec

    monkeypatch.setattr(sec.settings, "telnyx_api_key", "telnyx-key-value")
    stale = str(int(time.time()) - 9999)
    assert sec.TelephonySecurity.verify_telnyx_signature(b"{}", "sig", stale) is False


def test_telnyx_missing_headers_rejected_when_key_configured(monkeypatch):
    import app.telephony.security as sec

    monkeypatch.setattr(sec.settings, "telnyx_api_key", "telnyx-key-value")
    assert sec.TelephonySecurity.verify_telnyx_signature(b"{}", None, None) is False


def test_telnyx_valid_fresh_timestamp_accepted(monkeypatch):
    import time

    import app.telephony.security as sec

    monkeypatch.setattr(sec.settings, "telnyx_api_key", "telnyx-key-value")
    fresh = str(int(time.time()))
    assert sec.TelephonySecurity.verify_telnyx_signature(b"{}", "sig", fresh) is True


def test_recording_requires_explicit_two_party_consent():
    from app.telephony.security import TelephonySecurity

    assert TelephonySecurity.enforce_recording_policy(requested_recording=False) is False
    assert TelephonySecurity.enforce_recording_policy(
        requested_recording=True, caller_consented=True) is False
    assert TelephonySecurity.enforce_recording_policy(
        requested_recording=True, caller_consented=True, recipient_consented=True) is True


# --------------------------------------------------------------------------- #
# Endpoint integration: unsigned production webhooks rejected at the boundary
# --------------------------------------------------------------------------- #


def test_status_webhook_rejects_forged_signature(services_app_client, monkeypatch):
    import app.telephony.security as sec
    import app.telephony.webhook_service as whs

    _prod_security_posture(monkeypatch)
    # The router reads TelephonySecurity from the webhook_service namespace;
    # keep both pointed at the same class regardless of import order.
    monkeypatch.setattr(whs, "TelephonySecurity", sec.TelephonySecurity)
    r = services_app_client.post(
        "/api/v1/telephony/webhooks/status",
        data="CallSid=CA_forged&CallStatus=completed",
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "X-Twilio-Signature": "forged-signature=="},
    )
    assert r.status_code == 403, r.text


# --------------------------------------------------------------------------- #
# Provider-event idempotency: retries and out-of-order callbacks
# --------------------------------------------------------------------------- #


async def _place_call(client, user, payload: dict) -> dict:
    r = client.post(
        "/api/v1/telephony/calls",
        json=payload,
        headers=user["headers"],
    )
    assert r.status_code == 201, r.text
    return r.json()


def _status_post(client, sid: str, **fields):
    body = urlencode({"CallSid": sid, **fields})
    return client.post(
        "/api/v1/telephony/webhooks/status",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


@pytest.mark.asyncio
async def test_status_webhook_retry_is_idempotent(services_app_client, user):
    """The same 'completed' callback delivered twice must leave exactly one
    terminal transition (single usage record; duration not double-applied)."""
    call = await _place_call(services_app_client, user, {
        "to_number": "+919876543210", "caller_language": "en",
        "receiver_language": "hi", "caller_name": "Alice", "recipient_name": "Bob"})
    sid = call["call_sid"]
    call_id = uuid.UUID(call["id"])

    # First delivery + carrier retry of the exact same payload.
    first = _status_post(services_app_client, sid, CallStatus="completed", CallDuration=42)
    assert first.status_code == 200, first.text
    second = _status_post(services_app_client, sid, CallStatus="completed", CallDuration=42)
    assert second.status_code == 200, second.text

    detail = services_app_client.get(f"/api/v1/telephony/calls/{call_id}", headers=user["headers"])
    assert detail.status_code == 200
    assert detail.json()["status"] == "ended"
    assert detail.json()["duration_seconds"] == 42

    # Exactly one status_change event for the terminal transition.
    from app.db import models as M
    from app.db.session import db_session

    async with db_session() as db:
        res = await db.execute(
            M.CallEvent.__table__.select()
            .where(M.CallEvent.__table__.c.call_id == call_id)
        )
        events = res.fetchall()
    status_changes = [e for e in events if e.event_type == "status_change"]
    terminal = [e for e in status_changes if e.payload_json.get("status") == "ended"]
    assert len(terminal) == 1, f"terminal transition duplicated: {len(terminal)}"


@pytest.mark.asyncio
async def test_late_out_of_order_status_never_kills_an_ended_call(services_app_client, user):
    """in-progress arriving AFTER completed must not roll the call back."""
    call = await _place_call(services_app_client, user, {
        "to_number": "+8613800138000", "caller_language": "en", "receiver_language": "ja"})
    sid = call["call_sid"]
    call_id = call["id"]

    r1 = _status_post(services_app_client, sid, CallStatus="completed", CallDuration=30)
    assert r1.status_code == 200
    r2 = _status_post(services_app_client, sid, CallStatus="in-progress")
    assert r2.status_code == 200

    detail = services_app_client.get(f"/api/v1/telephony/calls/{call_id}", headers=user["headers"])
    assert detail.json()["status"] == "ended"
    assert detail.json()["duration_seconds"] == 30
