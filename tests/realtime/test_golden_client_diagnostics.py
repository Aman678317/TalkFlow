"""The golden call's own client, tested where no model weights exist.

`test_deployed_tree_golden_call.py` skips when the Argos/Piper/whisper packs are
absent — which is the `backend` CI lane and every fresh clone. Both things it now
relies on are pure client logic though, and both failed silently in run
`38502027159`: the socket was dropped by the server's 90 s heartbeat while the
test blamed the pipeline, and the assertion that fired listed event *names* only,
so the two `diagnostic` frames that would have said which stage stopped went
unread. These run in every lane, so a regression here is caught before the
expensive real-provider run.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import test_deployed_tree_golden_call as golden


class _FakeWs:
    """Records frames until it is told the socket is gone."""

    def __init__(self, fail_after: int):
        self.sent: list[str] = []
        self._fail_after = fail_after

    async def send(self, payload: str) -> None:
        if len(self.sent) >= self._fail_after:
            raise RuntimeError("connection is closed")
        self.sent.append(payload)


def test_client_keeps_the_socket_alive_the_way_the_browser_does():
    """A listener that sends nothing must still send heartbeats.

    The server closes a socket with no inbound frame after
    `RECEIVE_TIMEOUT_S = 90` (`services/api/app/realtime/ws.py:42`) and answers a
    `ping` with a `pong` (`ws.py:389`). Without the pinger an idle listener is cut
    off mid-run and the test reports a missing transcript it never waited for.
    """
    async def run():
        golden.HEARTBEAT_S = 0.01
        c = golden.Client("Listener")
        ws = c.ws = _FakeWs(fail_after=3)
        await c._pinger()          # returns once the fake socket dies
        return ws.sent

    sent = [json.loads(s) for s in asyncio.run(run())]
    assert len(sent) == 3, sent
    assert all(f["type"] == "ping" for f in sent), sent
    assert all("ts" in f for f in sent), sent


def test_timeout_names_the_stage_that_stopped(monkeypatch, tmp_path: Path):
    c = golden.Client("Beth")
    c.events = [
        {"version": 1, "type": "session.created", "data": {"participant_id": "p1"}},
        # Tree A flattens pipeline diagnostics onto the frame, not under `data`.
        {"version": 1, "type": "diagnostic", "stage": "stt",
         "provider": "faster_whisper", "ok": False, "error_class": "OSError"},
        {"version": 1, "type": "translation.failed", "target_language": "hi",
         "reason": "no_pack"},
        {"version": 1, "type": "reconnect.required", "data": {"reason": "heartbeat_timeout"}},
    ]
    log = tmp_path / "server.log"
    log.write_text("line one\nwhisper load failed: OSError disk full\n", encoding="utf-8")
    monkeypatch.setattr(golden, "SERVER_LOG", log)

    with pytest.raises(AssertionError) as exc:
        asyncio.run(c.expect(lambda e: e["type"] == "transcript.final",
                             timeout=0.1, what="the canonical Hindi transcript"))

    msg = str(exc.value)
    assert "no event matching the canonical Hindi transcript within 0s" in msg
    assert '"stage": "stt"' in msg, msg
    assert "translation.failed" in msg, msg
    assert "heartbeat_timeout" in msg, msg
    assert "whisper load failed" in msg, msg


def test_failure_context_survives_a_missing_log(monkeypatch, tmp_path: Path):
    """The report must still name the stage when the server wrote nothing yet."""
    monkeypatch.setattr(golden, "SERVER_LOG", tmp_path / "never-created.log")
    c = golden.Client("Beth")
    c.events = [{"type": "diagnostic", "stage": "mt", "ok": False}]
    with pytest.raises(AssertionError) as exc:
        asyncio.run(c.expect(lambda e: False, timeout=0.1, what="anything"))
    assert '"stage": "mt"' in str(exc.value)
    assert "unreadable" in str(exc.value)
