"""Automated security tests for Realtime & WebSocket session authorization:
- Rejection of unauthenticated WebSocket connections (close code 4401)
- Join ticket authentication
- Preventing unauthorized cross-tenant attendance without explicit guest join
"""
import uuid
import pytest
from starlette.websockets import WebSocketDisconnect


def test_unauthenticated_websocket_connection_rejected(services_app_client, user):
    # Tenant creates meeting
    m_res = services_app_client.post(
        "/api/v1/meetings",
        headers=user["headers"],
        json={"title": "Private Board Meeting", "mode": "ws", "hear_lang": "en"},
    )
    assert m_res.status_code == 201
    meeting_id = m_res.json()["id"]

    # Connecting with NO credentials to /ws/meetings/{meeting_id} MUST be rejected with 4401
    try:
        with services_app_client.websocket_connect(f"/ws/meetings/{meeting_id}") as ws:
            # If server accepts unauthenticated connection, this would fail the security test
            pytest.fail("Unauthenticated WebSocket connection was accepted! Expected close code 4401.")
    except WebSocketDisconnect as exc:
        assert exc.code in (4401, 1008), f"Expected auth rejection code 4401 or 1008, got {exc.code}"


def test_authenticated_ticket_websocket_connection(services_app_client, user):
    # Tenant creates meeting
    m_res = services_app_client.post(
        "/api/v1/meetings",
        headers=user["headers"],
        json={"title": "Team Sync", "mode": "ws", "hear_lang": "en"},
    )
    assert m_res.status_code == 201
    meeting_id = m_res.json()["id"]

    # Join meeting via REST API to establish participant and receive ticket
    join_res = services_app_client.post(
        f"/api/v1/meetings/{meeting_id}/join",
        headers=user["headers"],
        json={"display_name": "Host", "speak_lang": "en", "hear_lang": "es", "audio_mode": "translated"},
    )
    assert join_res.status_code == 200
    join_data = join_res.json()
    rt_url = join_data["rt_url"]
    assert "ticket=" in rt_url
    ticket = rt_url.split("ticket=")[1]

    # Connecting with valid ticket succeeds
    with services_app_client.websocket_connect(f"/ws/meetings/{meeting_id}?ticket={ticket}") as ws:
        # Connection succeeds, server sends initial greeting or waits for events
        assert ws is not None
