"""P4 §E3 — privacy + abuse gates (deterministic; real write/read paths).

Locks the invariants the phone-calling pipeline already claims, as gates:

- **Caller speech never persists as plaintext** (write path): a REAL media
  session (frames → RMS segmenter → transcribe hook → turn loop →
  ``MediaCallEventSink`` → ``call_events``) driven over the websocket with a
  transcribe hook returning deliberately PII-laden text — every persisted
  ledger row for that call is scanned and must not contain the caller's
  words; the utterance row must carry the exact ``text_fingerprint`` (length
  + sha256 of the stripped text), proving the gate is not vacuous.
- **The transcript API surfaces fingerprints, never caller plaintext**
  (read path): a seeded ai_agent-shaped ledger read back through the real
  router with real auth — the caller's words must be absent from the whole
  response body while the fingerprint and the verbatim agent line surface.
- **Unsigned flood**: N unsigned carrier callbacks under a forced production
  security posture — every probe 403s and ZERO CallSession/CallEvent rows
  appear (rejection happens before any state is created).
- **Garbage-signature flood**: N probes with a bogus ``X-Twilio-Signature`` —
  same verdict: all 403, zero state.

The webhook rate limit is forced high on every module-owned settings
binding (the known post-reload bleed convention), so each probe
deterministically reaches the signature check instead of an honest 429.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from urllib.parse import urlencode

import pytest

from test_agent_media_session import (
    FakeARI,
    _create_call_session,
    dial_asterisk_like_client,
    make_runtime,
    media_start_text,
)

CALLER_TEXT = ("I want to cancel my plan today, my card is 4111 1111 1111 1111"
               " and my name is Dana")
# distinctive, case-safe markers of the caller's words
_CALLER_TOKENS = ("4111", "dana", "cancel my plan")

_LOUD_FRAME = b"\xff\x7f" * 320      # 640 B slin16, all samples 0x7fff: RMS ≈ 32767
_SILENT_FRAME = b"\x00" * 640


# --------------------------------------------------------------------------- #
# gate 1 — caller speech never persists as plaintext (real write path)
# --------------------------------------------------------------------------- #


async def test_caller_speech_never_persists_as_plaintext(
        services_app_client, user) -> None:
    from sqlalchemy import select

    from app.db import models as M
    from app.db.session import db_session
    from app.telephony.ai_agent_graph import GraphConfig
    from app.telephony.media.agent_media_session import MediaCallEventSink
    from app.telephony.media.agent_turn_loop import text_fingerprint

    sid = f"talkflow-{uuid.uuid4()}"
    await _create_call_session(user["org_id"], user["user_id"], sid, "ai_agent")

    sink = MediaCallEventSink(sid)

    async def known_transcribe(segment: list[bytes]) -> str:
        return CALLER_TEXT          # deliberately PII-laden recognizer output

    runtime = make_runtime(FakeARI(), sink, spec_overrides={
        "transcribe": known_transcribe,
        "segment_wait_seconds": 0.15,
        "graph_config": GraphConfig(verify_identity=False),
    })
    port = await runtime.start()
    try:
        session = runtime.start_for_call(sid, "caller-gate")
        client = await dial_asterisk_like_client(port)
        await client.send(media_start_text(session.media_channel_id))
        for _ in range(100):
            if session.conn is not None:
                break
            await asyncio.sleep(0.01)
        assert session.conn is not None, "MEDIA_START never attached"

        # real speech then >= MIN_SILENCE_FRAMES (25) trailing silence: the
        # segment finalizes WHILE frames still flow (exactly the production
        # shape) — fewer silent frames would hit the turn deadline first and
        # the fail-closed empty utterance would fire before transcription
        await client.send("MEDIA_XON")
        for _ in range(8):
            await client.send(_LOUD_FRAME)
        for _ in range(30):
            await client.send(_SILENT_FRAME)
        await asyncio.sleep(0.6)

        # bounded nudges until the session ends: further silence yields the
        # empty utterance and the graph's own fail-closed escalation
        for _ in range(60):
            if session.finished.is_set():
                break
            await client.send(_SILENT_FRAME)
            await asyncio.sleep(0.05)
        await asyncio.wait_for(session.finished.wait(), timeout=10.0)
        assert session.outcome is not None
        assert session.outcome.terminal == "escalated"
        await client.close()
    finally:
        await runtime.stop()

    async with db_session() as db:
        res = await db.execute(
            select(M.CallSession.id).where(M.CallSession.call_sid == sid))
        call_id = res.scalars().one()
        res = await db.execute(
            select(M.CallEvent).where(M.CallEvent.call_id == call_id))
        rows = list(res.scalars().all())

    assert rows, "gate would be vacuous: the session persisted nothing"
    blobs = [json.dumps(r.payload_json, default=str).lower() for r in rows]
    for blob in blobs:
        for token in _CALLER_TOKENS:
            assert token not in blob, f"caller plaintext leaked: {blob}"

    utterances = [r for r in rows if r.event_type == "agent_turn_utterance"]
    assert len(utterances) == 1, "the gate is vacuous without a real utterance"
    fp = text_fingerprint(CALLER_TEXT)
    assert utterances[0].payload_json["text_sha256"] == fp["text_sha256"]
    assert utterances[0].payload_json["text_len"] == fp["text_len"]


# --------------------------------------------------------------------------- #
# gate 2 — the transcript API surfaces fingerprints, never caller plaintext
# --------------------------------------------------------------------------- #


async def test_transcript_api_never_leaks_caller_plaintext(
        services_app_client, user) -> None:
    from datetime import datetime, timedelta, timezone

    from app.db import models as M
    from app.db.session import db_session
    from app.telephony.media.agent_turn_loop import text_fingerprint

    sid = f"talkflow-{uuid.uuid4()}"
    async with db_session() as db:
        row = M.CallSession(
            org_id=uuid.UUID(user["org_id"]),
            created_by=uuid.UUID(user["user_id"]),
            call_sid=sid, from_number="1001", to_number="1002",
            mode="ai_agent", provider="asterisk", status="connected",
        )
        db.add(row)
        await db.flush()
        base = datetime.now(timezone.utc)
        db.add(M.CallEvent(
            call_id=row.id, event_type="agent_turn_said",
            payload_json={"node": "disclose", "action": "speak",
                          "text": "This is an automated AI assistant.",
                          "frames_rendered": 0, "tts": "absent"},
            created_at=base))
        fp = text_fingerprint(CALLER_TEXT)
        db.add(M.CallEvent(
            call_id=row.id, event_type="agent_turn_utterance",
            payload_json={"turn": 1, "text_len": fp["text_len"],
                          "text_sha256": fp["text_sha256"],
                          "confidence": 0.9, "frames": 30},
            created_at=base + timedelta(milliseconds=100)))
        await db.commit()

    r = services_app_client.get(
        f"/api/v1/telephony/calls/{row.id}/transcript",
        headers=user["headers"])
    assert r.status_code == 200, r.text
    body = r.text.lower()
    for token in _CALLER_TOKENS:
        assert token not in body, "caller plaintext leaked through the API"
    # non-vacuous: the fingerprint and the verbatim agent line DO surface
    assert fp["text_sha256"] in r.text
    assert "this is an automated ai assistant." in body


# --------------------------------------------------------------------------- #
# gates 3+4 — carrier-webhook floods create zero state
# --------------------------------------------------------------------------- #


def _force_flood_friendly_limits(monkeypatch) -> None:
    """Raise the webhook rate limit on every module-owned settings binding so
    a flood reaches the signature check deterministically (no 429 variance
    from session history or the 120/minute default)."""
    import app.config as cfg_mod
    import app.routers.telephony as tel_router

    for holder in (tel_router.settings, cfg_mod.settings):
        monkeypatch.setattr(holder, "rate_limit_telephony_webhook",
                            "100000/minute", raising=True)


def _force_prod_security(monkeypatch) -> None:
    import app.telephony.security as sec
    import app.telephony.webhook_service as whs

    monkeypatch.setattr(sec.settings, "telephony_verify_webhook_signatures",
                        True)
    monkeypatch.setattr(sec.settings, "twilio_auth_token", "prod-token-value")
    monkeypatch.setattr(sec.settings, "app_env", "production")
    # the router reads TelephonySecurity from the webhook_service namespace;
    # keep both pointed at the same class regardless of import order
    monkeypatch.setattr(whs, "TelephonySecurity", sec.TelephonySecurity)


async def _state_counts() -> tuple[int, int]:
    from sqlalchemy import func, select

    from app.db import models as M
    from app.db.session import db_session

    async with db_session() as db:
        calls = (await db.execute(
            select(func.count()).select_from(M.CallSession))).scalar_one()
        events = (await db.execute(
            select(func.count()).select_from(M.CallEvent))).scalar_one()
    return calls, events


async def _assert_flood_rejected_and_created_nothing(
        services_app_client, monkeypatch, *, signature: str | None) -> None:
    _force_flood_friendly_limits(monkeypatch)
    _force_prod_security(monkeypatch)

    before = await _state_counts()
    rejected = 0
    for i in range(25):
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if signature is not None:
            headers["X-Twilio-Signature"] = signature
        r = services_app_client.post(
            "/api/v1/telephony/webhooks/status",
            data=urlencode({"CallSid": f"CA_flood_{uuid.uuid4().hex[:12]}",
                            "CallStatus": "in-progress"}),
            headers=headers,
        )
        assert r.status_code == 403, f"probe {i}: {r.status_code} {r.text}"
        rejected += 1
    after = await _state_counts()
    assert rejected == 25
    assert after == before, "flood created state: {before} -> {after}"


async def test_unsigned_webhook_flood_creates_zero_state(
        services_app_client, monkeypatch) -> None:
    await _assert_flood_rejected_and_created_nothing(
        services_app_client, monkeypatch, signature=None)


async def test_garbage_signature_flood_creates_zero_state(
        services_app_client, monkeypatch) -> None:
    await _assert_flood_rejected_and_created_nothing(
        services_app_client, monkeypatch, signature="bogus-signature==")
