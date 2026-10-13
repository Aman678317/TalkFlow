"""Phase 4: the window a room discloses is the window that decides storage.

`GET /api/v1/meetings/{id}` now publishes the room's resolved policy, and the
lobby reads it out before anyone speaks. That is only worth telling if the write
path obeys the same number — and until now it read `settings.retention_audio_days`
while the deletion job reads the organization's and the room's override. A room
that says "no audio here" would still have had its voices stored for a week.

These tests drive one real utterance through the real stage body with a fake
object store, and ask the one question the disclosure makes a promise about:
was a WAV written, and does the caption row point at it?

Evidence level: the real ``MeetingPipeline._finalize_utterance``, the real
session manager and PCM-to-WAV conversion; a fake provider, a fake database and
a fake object store that records what it was asked to keep.
"""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from gt_ai.types import AudioChunk, DetectionResult, RouteDecision, TranscriptChunk

import app.realtime.pipeline as P
import app.storage as S
from app.realtime.session_manager import RtParticipant, RtSession, manager

# 1000 ms of 16 kHz mono PCM16: exactly 32 000 bytes.
AUDIO_1S = b"\x01\x02" * 16_000
SAID = "यह वाक्य बोला गया"


class FakeWs:
    async def send_text(self, payload: str) -> None:
        return None

    async def send_bytes(self, payload: bytes) -> None:
        return None


class FakeAI:
    async def transcribe(self, audio: bytes, sample_rate: int,
                         lang_hint: str | None = None):
        return (TranscriptChunk(text=SAID, language="hi", is_final=True,
                                confidence=0.9, model="fake-stt", provider="fake"),
                RouteDecision(provider="fake-stt", model="fake-stt-m", task="stt",
                              reason="test-fake"))

    async def detect_language(self, text: str) -> DetectionResult:
        return DetectionResult(language="hi", confidence=0.88, provider="fake-detect")

    async def synthesize_stream(self, text: str, lang: str, voice: str | None = None):
        async def stream():
            yield AudioChunk(data=b"\x54\x48" * 80, sample_rate=24000,
                             encoding="pcm_s16le", format="wav",
                             provider="fake-tts", model="fake-tts-m", duration_ms=250.0)
        return stream(), RouteDecision(provider="fake-tts", model="fake-tts-m",
                                       task="tts", reason="test-fake")

    def is_dev_mode(self, task) -> bool:
        return True


class FakeObjects:
    """What the deployment's object store was asked to keep."""

    def __init__(self) -> None:
        self.put: list[str] = []

    async def put_object(self, key: str, data: bytes, content_type: str) -> None:
        self.put.append(key)


def _wire(monkeypatch, objects: FakeObjects, statements: list) -> None:
    monkeypatch.setattr(P, "ai", FakeAI())

    class _Store:
        async def put(self, key: str, data: bytes, content_type: str) -> None:
            await objects.put_object(key, data, content_type)

    monkeypatch.setattr(S, "storage", lambda: _Store())

    @asynccontextmanager
    async def _fake_session(*_a, **_kw):
        async def _execute(stmt, *_a, **_kw):
            statements.append(str(stmt))
            return SimpleNamespace(scalar=lambda: 0)

        async def _commit():
            return None

        def _add(obj):
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

        yield SimpleNamespace(add=_add, commit=_commit, execute=_execute)

    monkeypatch.setattr(P, "db_session", _fake_session)


def _session(**fields) -> RtSession:
    return RtSession(session_id="sess-ret", meeting_id=uuid.uuid4(),
                     org_id=uuid.uuid4(), room_name="room", mode="ws", **fields)


async def _one_turn(pipe, speaker) -> None:
    u = P.UtteranceState(participant_id=speaker.participant_id,
                         capture_started=time.perf_counter() - 1.0,
                         started_at_ms=0, seq=1, in_speech=False)
    await pipe._finalize_utterance(
        speaker, u, audio_bytes=AUDIO_1S, start_ms=0,
        capture_started=u.capture_started, utterance_id=uuid.uuid4(), seq=1)


@pytest.fixture
def speaker():
    p = RtParticipant(participant_id=uuid.uuid4(), user_id=uuid.uuid4(),
                      display_name="Aman", speak_lang="hi", hear_lang="hi",
                      audio_mode="original", captions_enabled=True,
                      ws=FakeWs(), connected=True)
    return p


@pytest.mark.asyncio
async def test_a_room_that_keeps_no_audio_writes_no_recording(
        monkeypatch, speaker):
    """The room's 0 beats the deployment's 7.

    This is the case the disclosure would have lied about: a class that set
    `audio_days: 0` was told nothing was kept while the pipeline stored every
    voice against the global default.
    """
    objects, statements = FakeObjects(), []
    _wire(monkeypatch, objects, statements)
    monkeypatch.setattr(P.settings, "retention_audio_days", 7, raising=False)
    session = _session(retention_audio_days=0)
    manager.add_participant(session, speaker)

    await _one_turn(P.MeetingPipeline(session), speaker)

    assert objects.put == [], "a room with no audio window stored a recording"
    assert not [s for s in statements if "audio_object_key" in s], statements


@pytest.mark.asyncio
async def test_a_room_that_keeps_audio_stores_it_and_points_at_it(
        monkeypatch, speaker):
    """The other half: privacy settings that never write anything are not
    retention, they are a broken meeting."""
    objects, statements = FakeObjects(), []
    _wire(monkeypatch, objects, statements)
    monkeypatch.setattr(P.settings, "retention_audio_days", 7, raising=False)
    session = _session(retention_audio_days=7)
    manager.add_participant(session, speaker)

    await _one_turn(P.MeetingPipeline(session), speaker)

    assert len(objects.put) == 1, objects.put
    assert objects.put[0].endswith(".wav"), objects.put
    assert [s for s in statements if "audio_object_key" in s], (
        "the recording exists and nothing in the database names it")


@pytest.mark.asyncio
async def test_a_session_with_no_resolved_policy_falls_back_to_the_deployment(
        monkeypatch, speaker):
    """A session opened without the room's policy is still governed by something.

    `None` means nobody read a policy — a unit harness, a path that has not been
    wired yet — and the setting the operator configured has to be what applies,
    not an implicit decision to keep nothing.
    """
    objects, _statements = FakeObjects(), []
    _wire(monkeypatch, objects, _statements)
    monkeypatch.setattr(P.settings, "retention_audio_days", 7, raising=False)
    session = _session()
    manager.add_participant(session, speaker)

    await _one_turn(P.MeetingPipeline(session), speaker)

    assert len(objects.put) == 1, objects.put
