"""Phase 4, integration: what a hung-up socket is allowed to leave behind.

Two of the Phase 4 bullets — "health indicators mean the pipeline stage actually
ran" and "keep the original conversation available" — both depend on a meeting
knowing, accurately, who is still in it. Opening a real websocket in the CI suite
is what surfaced this: the disconnect handler ran its own database write inside
a task that was being cancelled, so the write died partway and left its
transaction open on a connection nobody would ever return. One dropped socket
was enough to block every later write in the process.

Evidence level: the real app, the real WebSocket handler, the real session
manager, the real pipeline.
"""
from __future__ import annotations

import time
import uuid

from app.realtime.session_manager import manager


def _meeting(client, headers: dict) -> str:
    r = client.post("/api/v1/meetings", headers=headers,
                    json={"title": "Drop test", "mode": "ws", "hear_lang": "en"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_hanging_up_releases_the_speaker_and_the_database(services_app_client, user):
    meeting_id = _meeting(services_app_client, user["headers"])
    join = services_app_client.post(
        f"/api/v1/meetings/{meeting_id}/join", headers=user["headers"],
        json={"display_name": "Host", "speak_lang": "hi", "hear_lang": "en",
              "audio_mode": "translated"})
    assert join.status_code == 200, join.text
    ticket = join.json()["rt_url"].split("ticket=")[1]

    with services_app_client.websocket_connect(
            f"/ws/meetings/{meeting_id}?ticket={ticket}") as ws:
        created = ws.receive_json()
    participant_id = created["data"]["participant_id"]

    # The task that read this participant's microphone has nothing left to read.
    session = manager.get_session_for_meeting(uuid.UUID(meeting_id))
    assert session is not None, "the socket closed, not the meeting"
    assert session.pipeline.speaker_tasks == {}
    assert session.pipeline.audio_queues == {}
    assert session.pipeline.vads == {}
    assert session.pipeline.utterances == {}
    assert not any(p.connected for p in session.participants.values())

    # ...and the write that records the departure actually committed. It runs
    # detached from the cancelled handler, so it needs a beat to land.
    row = None
    for _ in range(50):
        r = services_app_client.get(
            f"/api/v1/meetings/{meeting_id}/participants", headers=user["headers"])
        assert r.status_code == 200, r.text
        row = next((p for p in r.json() if p["id"] == participant_id), None)
        if row and row["status"] == "left":
            break
        time.sleep(0.1)
    assert row is not None and row["status"] == "left", \
        f"disconnect cleanup never completed: {row}"
