"""Phase 3 — turn segmentation numbers, measured rather than assumed.

The PDF asks for VAD end-of-speech and partial cadence "tuned from measured user
experience, not guesswork". Before this the numbers lived in two places that never
met: `EnergyVAD`'s constructor defaults carried the 250/500 ms thresholds and a
20 s cap the pipeline never overrode, while the speaker loop hard-coded its own
15 s monologue force-split — two turn-length limits that disagreed, and no setting
to retune either one per deployment.

What is measured here, on 16 kHz mono PCM16 fed in the 50 ms frames the browser's
AudioWorklet actually emits:

* **end-of-speech latency** — the delay between the speaker stopping and the turn
  being committed. It is `vad_min_silence_ms` rounded up to the VAD's 30 ms frame,
  plus up to two frames of slack because audio arrives in 50 ms chunks, so the
  setting *is* the latency budget, and raising it is felt as translation lag.
* **false-split threshold** — the shortest pause that still keeps one turn.
  Everything between these two numbers is the trade-off the setting makes.
* **minimum speech** — a burst shorter than `vad_min_speech_ms` never opens a
  turn, so a cough or a key click does not start a caption.
* **partial cadence** — how many live captions a turn gets per second, which is
  the other half of the same budget.

Not measured here, and still open: real speakers. These are the numbers of the
algorithm against synthetic tone, which is what can be measured without a room
full of people; the cadence chosen from them needs a human listening check
before it is called tuned.
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import numpy as np
import pytest
from gt_ai.vad import EnergyVAD, SpeechEvent, VadState

import app.realtime.pipeline as P
from app.config import settings
from app.realtime.session_manager import RtParticipant, RtSession, manager

# 16 kHz mono PCM16: 50 ms = 800 samples = 1600 bytes, the AudioWorklet frame.
CHUNK_BYTES = 1600
VAD_FRAME_MS = 30


def _tone(seconds: float, freq: float = 220, amp: float = 0.4) -> bytes:
    t = np.arange(int(seconds * 16000)) / 16000
    return (amp * 32767 * np.sin(2 * math.pi * freq * t)).astype(np.int16).tobytes()


def _silence(seconds: float) -> bytes:
    return np.zeros(int(seconds * 16000), dtype=np.int16).tobytes()


def _feed(vad: EnergyVAD, payload: bytes) -> list[SpeechEvent]:
    events: list[SpeechEvent] = []
    for i in range(0, len(payload), CHUNK_BYTES):
        events.extend(vad.process(payload[i:i + CHUNK_BYTES]))
    return events


@pytest.mark.parametrize("min_silence_ms", [300, 500, 800, 1200])
def test_end_of_speech_latency_is_the_setting_plus_frame_slack(min_silence_ms: int) -> None:
    """Measure what a given `vad_min_silence_ms` actually costs the listener."""
    vad = EnergyVAD(sample_rate=16000, min_silence_ms=min_silence_ms)
    _feed(vad, _tone(1.0))
    speech_end_ms = vad.clock_ms

    events = _feed(vad, _silence(min_silence_ms / 1000 + 0.3))
    ends = [e for e in events if e.state == VadState.SILENCE]
    assert len(ends) == 1, f"expected one turn end, got {ends}"

    latency = ends[0].timestamp_ms - speech_end_ms
    # Measured at 300/500/800/1200: 330/540/840/1230 ms. The VAD decides
    # on 30 ms frames, so it cannot answer sooner than the setting. It can be up
    # to two frames late: the silence only reaches `min_silence_ms` on a frame
    # boundary, and audio arrives in the browser's 50 ms chunks, so the chunk
    # that contains the transition is not processed until a further frame lands.
    assert min_silence_ms <= latency <= min_silence_ms + 2 * VAD_FRAME_MS


@pytest.mark.parametrize("pause_ms", [200, 300, 400])
def test_a_pause_shorter_than_the_setting_does_not_split_the_turn(pause_ms: int) -> None:
    """Inter-word hesitation must stay inside one turn at the shipped 500 ms."""
    vad = EnergyVAD(sample_rate=16000, min_silence_ms=500)
    events = []
    events += _feed(vad, _tone(0.8))
    events += _feed(vad, _silence(pause_ms / 1000))
    events += _feed(vad, _tone(0.8))

    assert [e.state for e in events] == [VadState.SPEECH], (
        f"a {pause_ms} ms pause split one sentence: {[e.state for e in events]}"
    )


def test_a_pause_longer_than_the_setting_ends_the_turn() -> None:
    vad = EnergyVAD(sample_rate=16000, min_silence_ms=500)
    events = []
    events += _feed(vad, _tone(0.8))
    events += _feed(vad, _silence(0.7))
    events += _feed(vad, _tone(0.8))

    assert [e.state for e in events] == [VadState.SPEECH, VadState.SILENCE,
                                         VadState.SPEECH]


@pytest.mark.parametrize("burst_ms", [50, 150, 200])
def test_a_burst_shorter_than_min_speech_never_opens_a_turn(burst_ms: int) -> None:
    vad = EnergyVAD(sample_rate=16000, min_speech_ms=250)
    events = _feed(vad, _tone(burst_ms / 1000))
    events += _feed(vad, _silence(0.5))
    assert not any(e.state == VadState.SPEECH for e in events), (
        f"a {burst_ms} ms transient opened a turn"
    )


def test_min_speech_setting_opens_the_turn_once_the_burst_is_long_enough() -> None:
    vad = EnergyVAD(sample_rate=16000, min_speech_ms=250)
    events = _feed(vad, _tone(0.6))
    assert any(e.state == VadState.SPEECH for e in events)


# --------------------------------------------------------------------------- #
# The settings must be what the deployed pipeline uses, not constructor defaults
# --------------------------------------------------------------------------- #

class FakeWs:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.frames: list[bytes] = []

    async def send_text(self, payload: str) -> None:
        self.events.append(json.loads(payload))

    async def send_bytes(self, payload: bytes) -> None:
        self.frames.append(payload)


@pytest.fixture
def session():
    return RtSession(session_id="sess-vad", meeting_id=uuid.uuid4(),
                     org_id=uuid.uuid4(), room_name="room", mode="ws")


@pytest.fixture
def no_db(monkeypatch):
    @asynccontextmanager
    async def _fake_session(*_a, **_kw):
        yield SimpleNamespace(add=lambda *_: None, commit=lambda: None,
                              execute=lambda *_: None)
    monkeypatch.setattr(P, "db_session", _fake_session)


@pytest.fixture
def speaker():
    return RtParticipant(participant_id=uuid.uuid4(), user_id=uuid.uuid4(),
                         display_name="Aman", speak_lang="hi", hear_lang="hi",
                         audio_mode="original", captions_enabled=True,
                         ws=FakeWs(), connected=True)


class OnsetVad:
    """Speech onset on the first frame, then silence forever: a held turn."""

    def __init__(self) -> None:
        self.clock_ms = 0
        self._fired = False

    def process(self, _pcm16: bytes) -> list[SpeechEvent]:
        if self._fired:
            return []
        self._fired = True
        return [SpeechEvent(state=VadState.SPEECH, timestamp_ms=0, energy=0.05)]


@pytest.mark.asyncio
async def test_the_pipeline_builds_its_vad_from_settings(session, speaker,
                                                        no_db, monkeypatch):
    """A setting nobody reads is documentation, not configuration."""
    monkeypatch.setattr(settings, "vad_min_silence_ms", 320, raising=False)
    monkeypatch.setattr(settings, "vad_min_speech_ms", 180, raising=False)
    monkeypatch.setattr(settings, "vad_max_speech_ms", 9000, raising=False)

    pipe = P.MeetingPipeline(session)
    pipe.start_speaker(speaker)
    try:
        vad = pipe.vads[speaker.participant_id]
        assert (vad.min_silence_ms, vad.min_speech_ms, vad.max_speech_ms) == (320, 180, 9000)
    finally:
        pipe.stop_speaker(speaker.participant_id)


@pytest.mark.asyncio
async def test_partial_caption_cadence_follows_the_setting(session, speaker,
                                                          no_db, monkeypatch):
    """Feed a held turn and count live captions over the same wall-clock window
    at two cadences. The setting has to change the observed rate."""
    # Broadcast goes to the session's participants, so the speaker has to be
    # registered for the caption to reach their socket.
    manager.add_participant(session, speaker)
    monkeypatch.setattr(P, "create_vad", lambda *_a, **_k: OnsetVad())

    pipe = P.MeetingPipeline(session)

    async def partial_transcribe(**_kw):
        # Whatever `_emit_partial` reads off the agent's contract.
        return SimpleNamespace(recognized_text="नमस्ते", source_language="hi",
                               confidence=0.9)

    monkeypatch.setattr(pipe.listening, "transcribe_partial", partial_transcribe)

    async def measure(interval_ms: int) -> int:
        monkeypatch.setattr(settings, "vad_partial_interval_ms", interval_ms, raising=False)
        pipe.start_speaker(speaker)
        try:
            # One second of audio at once: past the 0.8 s guard the partial path
            # requires, so only the cadence setting can gate what is emitted.
            await pipe.feed_audio(speaker.participant_id, b"\x01\x02" * 16000)
            for _ in range(6):
                await pipe.feed_audio(speaker.participant_id, b"\x01\x02" * 800)
                await asyncio.sleep(0.1)
            return len([e for e in speaker.ws.events
                        if e.get("type") == "transcript.partial"])
        finally:
            pipe.stop_speaker(speaker.participant_id)
            speaker.ws.events.clear()

    fast = await measure(100)
    slow = await measure(1200)
    assert fast >= 3, f"a 100 ms cadence produced {fast} partials in ~600 ms"
    assert slow <= 1, f"a 1200 ms cadence produced {slow} partials in ~600 ms"
