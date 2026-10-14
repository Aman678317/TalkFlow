"""Phase 4, integration: the health an operator reads is the pipeline's own.

Two surfaces, one source of truth:

* what the meeting is told when it joins (``SESSION_CREATED``'s ``ai`` block), and
* what an authenticated caller can poll afterwards
  (``GET /api/v1/meetings/{id}/realtime/health``)

used to be different things — the first said ``"translation": "active"`` before a
single byte had been transcribed, and the second did not exist, so the counters
that were genuinely derived (the bus's drops, the supervisor's stage failures)
could only be read from inside the process.

Evidence level: the real FastAPI app, the real WebSocket handler, the real
session manager and the real pipeline. Providers are the dev stand-ins the test
harness configures, which is why these assertions pin the *stage bookkeeping*
and not any engine's quality.
"""
from __future__ import annotations

import json
import uuid

import pytest

from app.realtime.session_manager import manager


def _meeting(client, headers: dict) -> str:
    r = client.post("/api/v1/meetings", headers=headers,
                    json={"title": "Health check", "mode": "ws", "hear_lang": "en"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _ticket(client, headers: dict, meeting_id: str) -> str:
    r = client.post(f"/api/v1/meetings/{meeting_id}/join", headers=headers,
                    json={"display_name": "Host", "speak_lang": "hi",
                          "hear_lang": "en", "audio_mode": "translated"})
    assert r.status_code == 200, r.text
    return r.json()["rt_url"].split("ticket=")[1]


def test_a_joining_participant_is_told_that_nothing_has_run(services_app_client, user):
    """The payload that replaced ``"translation": "active"``.

    Joining is when the old claim was loudest: a brand new meeting has produced
    no transcript, no translation and no speech, and said it was active.
    """
    meeting_id = _meeting(services_app_client, user["headers"])
    ticket = _ticket(services_app_client, user["headers"], meeting_id)

    with services_app_client.websocket_connect(
            f"/ws/meetings/{meeting_id}?ticket={ticket}") as ws:
        created = ws.receive_json()

    assert created["type"] == "session.created"
    ai = created["data"]["ai"]
    assert {s["status"] for s in ai["stages"].values()} == {"not_yet_ran"}
    assert ai["healthy"] is True
    # The one word the old payload hardcoded is now absent from the evidence.
    assert "active" not in json.dumps(ai["stages"])


def test_the_health_endpoint_agrees_with_the_join_message(services_app_client, user):
    """One derived object, two doors. If these two ever disagree about what has
    run, the meeting is being told something the operator cannot verify."""
    meeting_id = _meeting(services_app_client, user["headers"])
    ticket = _ticket(services_app_client, user["headers"], meeting_id)

    with services_app_client.websocket_connect(
            f"/ws/meetings/{meeting_id}?ticket={ticket}") as ws:
        created = ws.receive_json()
        r = services_app_client.get(
            f"/api/v1/meetings/{meeting_id}/realtime/health", headers=user["headers"])
        assert r.status_code == 200, r.text
        body = r.json()

    assert body["live"] is True
    assert body["meeting_id"] == meeting_id
    assert body["stages"] == created["data"]["ai"]["stages"]
    assert manager.get_session_for_meeting(uuid.UUID(meeting_id)) is not None


def test_realtime_health_requires_a_principal(services_app_client, user):
    meeting_id = _meeting(services_app_client, user["headers"])
    r = services_app_client.get(f"/api/v1/meetings/{meeting_id}/realtime/health")
    assert r.status_code == 401


def test_realtime_health_does_not_cross_tenants(services_app_client, user,
                                                second_user):
    meeting_id = _meeting(services_app_client, user["headers"])
    r = services_app_client.get(f"/api/v1/meetings/{meeting_id}/realtime/health",
                                headers=second_user["headers"])
    # Another org's meeting is not found, not forbidden: this route must not
    # become a way to probe which meeting ids exist.
    assert r.status_code == 404, r.text


def test_a_meeting_with_no_session_in_this_process_says_so(services_app_client, user):
    """Health is per-process. A meeting hosted on another replica is not this
    replica's idle-and-fine meeting, and pretending otherwise is the same lie in
    a different costume."""
    meeting_id = _meeting(services_app_client, user["headers"])
    r = services_app_client.get(f"/api/v1/meetings/{meeting_id}/realtime/health",
                                headers=user["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["live"] is False
    assert body["stages"] == {}


@pytest.mark.parametrize("path", ["/api/v1/health", "/ready"])
def test_process_health_still_claims_nothing_about_stages(services_app_client, path):
    """/health and /ready check the process and its dependencies. They are not
    where a stage's status gets invented — which is how "active" reached a
    browser in the first place."""
    r = services_app_client.get(path)
    assert r.status_code in (200, 503), r.text
    assert "active" not in r.text
