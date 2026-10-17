"""Phase 4: a reconnecting listener has to land back in the same meeting.

The guide asks for a reconnection test. This is the one that matters, because
the resume path is where two features meet and neither owns the seam: Phase 4's
departure release wipes everything the meeting holds for a `participant_id` when
its socket goes away, and the browser reconnects with **the same
`participant_id`** — the JWT path looks the participant row up again. So the
handover has to release the dead connection without taking the person with it,
and the reconnecting client has to be handed back what it missed while it was
gone.

Two failure modes this covers and no test did:

* a superseded socket's cleanup running after the new one registered, deleting
  the speaker loop the new socket just started (the guard in the handler's
  ``finally`` is what stops it, and it is exactly the kind of condition a
  hardcoded "works" hides);
* a resume that reports `replayed: 0` because the replay buffer was appended to
  only for unsequenced events — the listener would silently lose the sentences
  spoken while they were disconnected.

Evidence level: the real app, the real WebSocket handler, real session manager,
real pipeline. The providers are this environment's dev stand-ins, which is
honest as long as the assertions are about identity, sequencing and replay — not
about translation quality.
"""
from __future__ import annotations

import uuid

from app.realtime.session_manager import manager


def _join(client, headers, meeting_id, *, speak="hi", hear="en") -> dict:
    r = client.post(f"/api/v1/meetings/{meeting_id}/join", headers=headers,
                    json={"display_name": "Aman", "speak_lang": speak,
                          "hear_lang": hear, "audio_mode": "translated"})
    assert r.status_code == 200, r.text
    return r.json()


def _meeting(client, headers) -> str:
    r = client.post("/api/v1/meetings", headers=headers,
                    json={"title": "Reconnect test", "mode": "ws", "hear_lang": "en"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _say(ws, text: str, language: str = "hi") -> None:
    ws.send_json({"type": "transcript.inject",
                  "data": {"text": text, "language": language}})


def _until(ws, predicate, what: str, limit: int = 120) -> dict:
    """Read frames until one matches, or give up with a useful message."""
    seen = []
    for _ in range(limit):
        evt = ws.receive_json()
        seen.append(evt.get("type"))
        if predicate(evt):
            return evt
    raise AssertionError(f"never got {what}; saw {seen[-20:]}")


# --------------------------------------------------------------------------- #
# identity across the gap
# --------------------------------------------------------------------------- #

def test_reconnecting_returns_the_same_participant(services_app_client, user):
    """Not a new attendee: the same person, with the same place in the room.

    Everything the browser correlates captions by — the speaker id on each turn,
    its own resume position — is only stable if the reconnect resolves back to
    the participant the first join issued.
    """
    meeting_id = _meeting(services_app_client, user["headers"])
    first = _join(services_app_client, user["headers"], meeting_id)
    pid = first["participant_id"]

    with services_app_client.websocket_connect(
            f"/ws/meetings/{meeting_id}?ticket={first['rt_url'].split('ticket=')[1]}"
    ) as ws1:
        created = _until(ws1, lambda e: e["type"] == "session.created",
                         "session.created")
        assert created["data"]["participant_id"] == pid

    with services_app_client.websocket_connect(
            f"/ws/meetings/{meeting_id}?token={user['token']}"
    ) as ws2:
        back = _until(ws2, lambda e: e["type"] == "session.created",
                      "session.created on the reconnect")

    assert back["data"]["participant_id"] == pid, (
        "the socket came back as somebody else — every caption the client "
        "replayed is now attributed to a stranger")


def test_the_dead_socket_does_not_take_the_reconnected_one_with_it(
        services_app_client, user):
    """Supersession, in order: the new socket is live while the old one dies.

    Two connections for one participant, the old handler's ``finally`` running
    after the new one has attached and started its speaker loop. If that cleanup
    called the departure release, the reconnected participant would have no
    audio queue, no VAD and no utterance state, and their microphone would be
    silently discarded for the rest of the meeting.
    """
    meeting_id = _meeting(services_app_client, user["headers"])
    first = _join(services_app_client, user["headers"], meeting_id)
    ticket = first["rt_url"].split("ticket=")[1]
    pid = first["participant_id"]

    with services_app_client.websocket_connect(
            f"/ws/meetings/{meeting_id}?ticket={ticket}") as ws1:
        _until(ws1, lambda e: e["type"] == "session.created", "first session.created")

        with services_app_client.websocket_connect(
                f"/ws/meetings/{meeting_id}?token={user['token']}") as ws2:
            _until(ws2, lambda e: e["type"] == "session.created",
                   "second session.created")

            session = manager.get_session_for_meeting(uuid.UUID(meeting_id))
            pipe = session.pipeline
            assert str(pid) in session.participants
            assert pipe is not None and pipe.speaker_tasks, (
                "the speaker loop is not running for the live socket")

            _say(ws2, "दूसरा बारी", language="hi")
            late = _until(ws2, lambda e: e["type"] == "transcript.final",
                          "the turn spoken after the takeover")

    assert late["data"]["speaker_id"] == str(pid)
    # The turn the room moved on with is still being delivered to the survivor.
    assert late["data"]["text"]


# --------------------------------------------------------------------------- #
# what was said while the listener was gone
# --------------------------------------------------------------------------- #

def test_a_resume_gets_back_the_captions_it_missed(services_app_client, user):
    """`replayed` has to mean sentences, not a count of nothing.

    The client stores the highest sequence it played and asks for everything
    after it. If the server's replay buffer never held the sequenced events, the
    resume answers with an empty list and a politely silent hole in the
    transcript — which is the worst possible failure, because nothing looks
    broken.

    Two turns, not one, because the watermark has to be a real one: a client
    that has played nothing asks for sequence 0, and the server treats that as
    "there is nothing to catch you up on" and replies to none of it.
    """
    meeting_id = _meeting(services_app_client, user["headers"])
    first = _join(services_app_client, user["headers"], meeting_id)
    pid = first["participant_id"]
    ticket = first["rt_url"].split("ticket=")[1]

    with services_app_client.websocket_connect(
            f"/ws/meetings/{meeting_id}?ticket={ticket}") as ws:
        _until(ws, lambda e: e["type"] == "session.created", "session.created")

        _say(ws, "पहली बात")
        played_evt = _until(ws, lambda e: e["type"] == "transcript.final",
                            "the first turn")
        # The watermark a browser would actually hold: the highest sequence it
        # took off the wire.
        played = played_evt["sequence"]
        assert played > 0, "a caption arrived unsequenced, so resume has no watermark"

        _say(ws, "वह बात जो कनेक्शन टूटने के बीच में हुई")
        missed = _until(ws, lambda e: e["type"] == "transcript.final"
                        and e["data"].get("text") != played_evt["data"]["text"],
                        "the second turn")

    with services_app_client.websocket_connect(
            f"/ws/meetings/{meeting_id}?token={user['token']}") as ws:
        _until(ws, lambda e: e["type"] == "session.created",
               "session.created on resume")
        # The browser's own reconnect: a fresh socket, the participant id it was
        # given, and the last sequence it actually played. Flat keys, which the
        # protocol folds into `data` server-side.
        ws.send_json({"type": "session.join", "participant_id": str(pid),
                      "display_name": "Aman", "speaking_language": "hi",
                      "listening_language": "en", "audio_mode": "translated",
                      "last_sequence": played, "resume": True})
        resumed = _until(ws, lambda e: e["type"] == "session.resumed"
                         and "replayed" in e["data"], "a resume ack")
        assert resumed["data"]["replayed"] >= 1, (
            f"the meeting replayed nothing after sequence {played}: "
            f"{resumed['data']}")
        replayed = _until(ws, lambda e: e["type"] == "transcript.final"
                          and e["data"].get("text") == "वह बात जो कनेक्शन टूटने के बीच में हुई",
                          "the caption spoken during the disconnect")
        assert replayed["data"]["utterance_id"] == missed["data"]["utterance_id"]
