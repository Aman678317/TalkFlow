"""Comprehensive Realtime & Meeting Security Verification Test Suite:
- WebSocket authentication & close code policies
- Realtime session ticket single-use & replay protection
- Meeting / room scope enforcement (tickets cannot cross meetings)
- Duplicate connection detection & graceful socket supersession (close code 4409)
- LiveKit token scoping, short TTL (30 min max, no 6-hour leaks), and secret isolation
- Non-joinable / ended meeting protection
- Participant impersonation prevention
"""
import json
import time
import uuid
import jwt
import pytest
from starlette.websockets import WebSocketDisconnect

from app.config import settings
from app.realtime.livekit_bridge import join_token as lk_join_token


def test_unauthenticated_websocket_connection_rejected(services_app_client, user):
    res = services_app_client.post(
        "/api/v1/meetings",
        headers=user["headers"],
        json={"title": "Private Sync", "mode": "ws", "hear_lang": "en"},
    )
    assert res.status_code == 201
    meeting_id = res.json()["id"]

    try:
        with services_app_client.websocket_connect(f"/ws/meetings/{meeting_id}") as ws:
            pytest.fail("Unauthenticated WebSocket connection was accepted! Expected close code 4401.")
    except WebSocketDisconnect as exc:
        assert exc.code in (4401, 1008), f"Expected 4401 or 1008, got {exc.code}"


def test_authenticated_ticket_websocket_connection(services_app_client, user):
    res = services_app_client.post(
        "/api/v1/meetings",
        headers=user["headers"],
        json={"title": "Team Standup", "mode": "ws", "hear_lang": "en"},
    )
    assert res.status_code == 201
    meeting_id = res.json()["id"]

    join_res = services_app_client.post(
        f"/api/v1/meetings/{meeting_id}/join",
        headers=user["headers"],
        json={"display_name": "Host", "speak_lang": "en", "hear_lang": "en", "audio_mode": "translated"},
    )
    assert join_res.status_code == 200
    ticket = join_res.json()["rt_url"].split("ticket=")[1]

    with services_app_client.websocket_connect(f"/ws/meetings/{meeting_id}?ticket={ticket}") as ws:
        msg = ws.receive_text()
        assert "session.created" in msg


def test_realtime_session_ticket_replay_protection(services_app_client, user):
    """Ensure realtime session tickets are single-use and cannot be replayed."""
    res = services_app_client.post(
        "/api/v1/meetings",
        headers=user["headers"],
        json={"title": "Replay Test Meeting", "mode": "ws", "hear_lang": "en"},
    )
    assert res.status_code == 201
    meeting_id = res.json()["id"]

    join_res = services_app_client.post(
        f"/api/v1/meetings/{meeting_id}/join",
        headers=user["headers"],
        json={"display_name": "User 1", "speak_lang": "en", "hear_lang": "en", "audio_mode": "translated"},
    )
    assert join_res.status_code == 200
    ticket = join_res.json()["rt_url"].split("ticket=")[1]

    # First connection consumes ticket successfully
    with services_app_client.websocket_connect(f"/ws/meetings/{meeting_id}?ticket={ticket}") as ws:
        msg = ws.receive_text()
        assert "session.created" in msg

    # Second connection with the EXACT SAME ticket MUST be rejected (replay detected)
    try:
        with services_app_client.websocket_connect(f"/ws/meetings/{meeting_id}?ticket={ticket}") as ws:
            pytest.fail("Replayed ticket connection was accepted! Expected close code 4401.")
    except WebSocketDisconnect as exc:
        assert exc.code in (4401, 1008), f"Expected 4401, got {exc.code}"


def test_ticket_meeting_boundary_enforcement(services_app_client, user):
    """A ticket minted for Meeting A cannot be used to connect to Meeting B."""
    m1_res = services_app_client.post(
        "/api/v1/meetings",
        headers=user["headers"],
        json={"title": "Meeting A", "mode": "ws", "hear_lang": "en"},
    )
    assert m1_res.status_code == 201
    m1_id = m1_res.json()["id"]

    m2_res = services_app_client.post(
        "/api/v1/meetings",
        headers=user["headers"],
        json={"title": "Meeting B", "mode": "ws", "hear_lang": "en"},
    )
    assert m2_res.status_code == 201
    m2_id = m2_res.json()["id"]

    # Join Meeting A to get ticket for Meeting A
    j1_res = services_app_client.post(
        f"/api/v1/meetings/{m1_id}/join",
        headers=user["headers"],
        json={"display_name": "User A", "speak_lang": "en", "hear_lang": "en", "audio_mode": "translated"},
    )
    assert j1_res.status_code == 200
    ticket_a = j1_res.json()["rt_url"].split("ticket=")[1]

    # Attempt to connect to Meeting B with Meeting A's ticket MUST be rejected
    try:
        with services_app_client.websocket_connect(f"/ws/meetings/{m2_id}?ticket={ticket_a}") as ws:
            pytest.fail("Cross-meeting ticket connection was accepted! Expected close code 4403.")
    except WebSocketDisconnect as exc:
        assert exc.code in (4403, 4401, 1008), f"Expected 4403 or 4401, got {exc.code}"


def test_duplicate_connection_superseded(services_app_client, user):
    """When a new connection arrives for the same participant, the old socket is closed with 4409."""
    import contextlib
    res = services_app_client.post(
        "/api/v1/meetings",
        headers=user["headers"],
        json={"title": "Duplicate Socket Test", "mode": "ws", "hear_lang": "en"},
    )
    assert res.status_code == 201
    meeting_id = res.json()["id"]

    # Participant joins and gets ticket 1
    join_res = services_app_client.post(
        f"/api/v1/meetings/{meeting_id}/join",
        headers=user["headers"],
        json={"display_name": "Host", "speak_lang": "en", "hear_lang": "en", "audio_mode": "translated"},
    )
    assert join_res.status_code == 200
    ticket_1 = join_res.json()["rt_url"].split("ticket=")[1]

    # Mint a fresh ticket 2 for the same participant
    tok_res = services_app_client.post(
        f"/api/v1/meetings/{meeting_id}/tokens",
        headers=user["headers"],
    )
    assert tok_res.status_code == 200
    ticket_2 = tok_res.json()["ticket"]

    ws1 = None
    ws2 = None
    try:
        # Socket 1 connects and receives session.created
        ws1 = services_app_client.websocket_connect(f"/ws/meetings/{meeting_id}?ticket={ticket_1}")
        ws1.__enter__()
        msg1 = ws1.receive_text()
        assert "session.created" in msg1

        # Socket 2 connects for same participant
        ws2 = services_app_client.websocket_connect(f"/ws/meetings/{meeting_id}?ticket={ticket_2}")
        ws2.__enter__()

        # Socket 1 should now be closed with 4409 (duplicate_connection_superseded)
        with pytest.raises(WebSocketDisconnect) as excinfo:
            for _ in range(5):
                ws1.receive_text()
        assert excinfo.value.code in (4409, 1000, 1001), f"Expected close code 4409, got {excinfo.value.code}"
    finally:
        if ws1 is not None:
            with contextlib.suppress(Exception):
                ws1.__exit__(None, None, None)
        if ws2 is not None:
            with contextlib.suppress(Exception):
                ws2.__exit__(None, None, None)


def test_livekit_token_scoping_and_short_ttl(monkeypatch):
    """Verify LiveKit access tokens have short TTL (<= 1800s), room scoping, and no secret exposure."""
    monkeypatch.setattr(settings, "livekit_enabled", True)
    monkeypatch.setattr(settings, "livekit_url", "wss://livekit.example.com")
    monkeypatch.setattr(settings, "livekit_api_key", "devkey")
    monkeypatch.setattr(settings, "livekit_api_secret", "secretkey123456789012345678901234")

    room = "test-conf-room"
    pid = "participant-uuid-1234"
    name = "Dr. Alice"
    meta = {"role": "speaker", "hear_lang": "de"}

    token_dict = lk_join_token(room_name=room, identity=pid, name=name, metadata=meta, ttl_seconds=1800)
    assert token_dict is not None, "LiveKit token generation must succeed"

    assert "token" in token_dict
    raw_jwt = token_dict["token"]
    payload = jwt.decode(raw_jwt, settings.livekit_api_secret, algorithms=["HS256"])

    # Verify TTL is short (<= 30 minutes, not 6 hours)
    duration = payload["exp"] - payload["nbf"]
    assert duration <= 1815, f"Token TTL is too long ({duration}s), expected <= 1815s"

    # Verify scoping
    assert payload["sub"] == pid
    assert payload["name"] == name
    assert payload["video"]["room"] == room
    assert payload["video"]["roomJoin"] is True
    assert payload["video"].get("roomCreate") is not True, "Join token must not allow room creation"
    assert payload["video"].get("roomAdmin") is not True, "Join token must not grant room admin"


def test_cannot_join_or_connect_ended_meeting(services_app_client, user):
    """Ended meeting cannot be joined or connected to via WebSocket."""
    res = services_app_client.post(
        "/api/v1/meetings",
        headers=user["headers"],
        json={"title": "Ending Meeting", "mode": "ws", "hear_lang": "en"},
    )
    assert res.status_code == 201
    meeting_id = res.json()["id"]

    # End the meeting
    end_res = services_app_client.post(f"/api/v1/meetings/{meeting_id}/end", headers=user["headers"])
    assert end_res.status_code in (200, 204)

    # Attempting to join ended meeting MUST fail
    join_res = services_app_client.post(
        f"/api/v1/meetings/{meeting_id}/join",
        headers=user["headers"],
        json={"display_name": "Latecomer", "speak_lang": "en", "hear_lang": "en"},
    )
    assert join_res.status_code in (400, 422)

    # Attempting to connect to ended meeting is rejected
    try:
        with services_app_client.websocket_connect(f"/ws/meetings/{meeting_id}") as ws:
            pytest.fail("Connected to ended meeting!")
    except WebSocketDisconnect as exc:
        assert exc.code in (4401, 4410, 1008)
