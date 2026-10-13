"""Phase 3 — a caption has to say *which turn* it describes and *when* it was said.

The exit gate says "captions align". Alignment is only possible if the wire events
carry the turn's identity and timeline, because the three events that build one
caption arrive out of order by nature: the partial while the speaker is still
talking, the final when they stop, and the translation some hundreds of ms later
after the *next* speaker may already have started. Before this, `transcript.final`
named the utterance but not when it happened, `translation.final` carried a
segment id the client could not match to a caption id, and `latency.report` had
neither — so the browser attached a translation to "the last untranslated caption
from a speaker with that display name", which is a guess about a timeline nobody
was told.

These tests drive the real stage bodies and the real ``SessionManager`` routing
with fake providers, and assert the fields the browser is allowed to depend on.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from gt_ai.types import (
    AudioChunk, DetectionResult, RouteDecision, TranscriptChunk, TranslationResult,
)

import app.realtime.pipeline as P
from app.config import settings
from app.realtime.session_manager import RtParticipant, RtSession, manager

# 1000 ms of 16 kHz mono PCM16: exactly 32 000 bytes.
AUDIO_1S = b"\x01\x02" * 16_000
AUDIO_MS = len(AUDIO_1S) / 32.0


class FakeWs:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.frames: list[bytes] = []

    async def send_text(self, payload: str) -> None:
        self.events.append(json.loads(payload))

    async def send_bytes(self, payload: bytes) -> None:
        self.frames.append(payload)


def _decision(provider: str, task: str) -> RouteDecision:
    return RouteDecision(provider=provider, model=f"{provider}-m", task=task,
                         reason="test-fake")


class FakeAI:
    """One transcription, one voice: enough to walk a turn to the wire."""

    def __init__(self, text: str = "नमस्ते", language: str = "hi") -> None:
        self.text = text
        self.language = language

    async def transcribe(self, audio: bytes, sample_rate: int,
                         lang_hint: str | None = None):
        return (TranscriptChunk(text=self.text, language=self.language, is_final=True,
                                confidence=0.9, model="fake-stt", provider="fake"),
                _decision("fake-stt", "stt"))

    async def detect_language(self, text: str) -> DetectionResult:
        return DetectionResult(language=self.language, confidence=0.88,
                               provider="fake-detect")

    async def synthesize_stream(self, text: str, lang: str, voice: str | None = None):
        async def stream():
            yield AudioChunk(data=b"\x54\x48" * 80, sample_rate=24000,
                             encoding="pcm_s16le", format="wav", provider="fake-tts",
                             model="fake-tts-m", duration_ms=250.0)
        return stream(), _decision("fake-tts", "tts")

    def is_dev_mode(self, task) -> bool:
        return True


@pytest.fixture
def session():
    return RtSession(session_id="sess-cap", meeting_id=uuid.uuid4(),
                     org_id=uuid.uuid4(), room_name="room", mode="ws")


@pytest.fixture
def no_db(monkeypatch):
    """A fake session that still gives the segment a real id, because the caption
    events are supposed to carry one."""
    class _Result:
        def scalar(self):
            return 0

    @asynccontextmanager
    async def _fake_session(*_a, **_kw):
        def _add(obj):
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

        async def _execute(*_a, **_kw):
            return _Result()

        async def _commit():
            return None

        yield SimpleNamespace(add=_add, commit=_commit, execute=_execute)
    monkeypatch.setattr(P, "db_session", _fake_session)
    # The audio artifact upload is retention-gated and must not run here.
    monkeypatch.setattr(settings, "retention_audio_days", 0, raising=False)


@pytest.fixture
def speaker():
    return RtParticipant(participant_id=uuid.uuid4(), user_id=uuid.uuid4(),
                         display_name="Aman", speak_lang="hi", hear_lang="hi",
                         audio_mode="original", captions_enabled=True,
                         ws=FakeWs(), connected=True)


@pytest.fixture
def listener():
    """Someone hearing English, so the turn actually fans out."""
    return RtParticipant(participant_id=uuid.uuid4(), user_id=uuid.uuid4(),
                         display_name="Beth", speak_lang="en", hear_lang="en",
                         audio_mode="translated", captions_enabled=True,
                         ws=FakeWs(), connected=True)


def _utt(speaker: RtParticipant, *, held_ms: int, seq: int = 1) -> P.UtteranceState:
    """An utterance the speaker loop has been holding for `held_ms`."""
    return P.UtteranceState(
        participant_id=speaker.participant_id,
        capture_started=time.perf_counter() - held_ms / 1000.0,
        started_at_ms=0, seq=seq, in_speech=False)


def _events(ws: FakeWs, event_type: str) -> list[dict]:
    return [e for e in ws.events if e.get("type") == event_type]


def _fake_translate(monkeypatch) -> None:
    async def fake_translate(db, text, src, tgt, ctx):
        return SimpleNamespace(result=TranslationResult(
            text=f"[{tgt}] {text}", source_lang=src, target_lang=tgt,
            model="fake-mt", provider="fake-mt", latency_ms=5.0, quality_flags=[]))

    monkeypatch.setattr(P, "translate_text", fake_translate)


async def _drain(pipe) -> None:
    """Wait for the fan-out tasks a committed turn launched; they are created
    concurrently, so their caption events do not exist yet when it returns."""
    deadline = time.time() + 10.0
    while pipe.translation_tasks and time.time() < deadline:
        await asyncio.gather(*list(pipe.translation_tasks.values()),
                             return_exceptions=True)
    assert not pipe.translation_tasks, "fan-out never came home"


async def _run_turn(pipe, speaker, *, held_ms: int, seq: int = 1,
                    audio: bytes = AUDIO_1S) -> str:
    """Finalize one turn the way the speaker loop does, and return its id."""
    u = _utt(speaker, held_ms=held_ms, seq=seq)
    utterance_id = uuid.uuid4()
    await pipe._finalize_utterance(
        speaker, u, audio_bytes=audio, start_ms=0,
        capture_started=u.capture_started, utterance_id=utterance_id, seq=seq)
    await _drain(pipe)
    return str(utterance_id)


@pytest.mark.asyncio
async def test_transcript_final_names_the_turn_and_when_it_was_said(
        session, speaker, listener, no_db, monkeypatch):
    manager.add_participant(session, speaker)
    manager.add_participant(session, listener)
    monkeypatch.setattr(P, "ai", FakeAI())
    _fake_translate(monkeypatch)

    pipe = P.MeetingPipeline(session)
    uid = await _run_turn(pipe, speaker, held_ms=1500)

    finals = _events(speaker.ws, "transcript.final")
    assert len(finals) == 1
    final = finals[0]["data"]
    assert final["utterance_id"] == uid
    # The turn began 1.5 s before STT ran, so the start it reports has to sit
    # there on the wall clock, not at 0 and not at the VAD's own frame counter.
    assert abs(final["start_wall_ms"] - (time.time() * 1000 - 1500)) < 250
    # Duration is the audio, not the elapsed time: a turn that took longer to
    # transcribe is not a longer sentence.
    assert final["duration_ms"] == round(AUDIO_MS)


@pytest.mark.asyncio
async def test_translation_final_carries_the_same_identity_as_its_source_caption(
        session, speaker, listener, no_db, monkeypatch):
    manager.add_participant(session, speaker)
    manager.add_participant(session, listener)
    monkeypatch.setattr(P, "ai", FakeAI())
    _fake_translate(monkeypatch)

    pipe = P.MeetingPipeline(session)
    uid = await _run_turn(pipe, speaker, held_ms=900)

    source = _events(speaker.ws, "transcript.final")[0]["data"]
    translated = _events(listener.ws, "translation.final")[0]["data"]

    # The client joins these two on ids, so they must agree without a heuristic.
    assert translated["utterance_id"] == source["utterance_id"] == uid
    assert translated["segment_id"] == source["segment_id"]
    assert translated["seq"] == source["seq"]
    assert translated["start_wall_ms"] == source["start_wall_ms"]
    assert translated["duration_ms"] == source["duration_ms"]
    # ...and it is the *source* language that identifies what was spoken.
    assert translated["source_language"] == source["language"]


@pytest.mark.asyncio
async def test_latency_report_is_attributable_to_the_caption_it_delayed(
        session, speaker, listener, no_db, monkeypatch):
    manager.add_participant(session, speaker)
    manager.add_participant(session, listener)
    monkeypatch.setattr(P, "ai", FakeAI())
    _fake_translate(monkeypatch)

    pipe = P.MeetingPipeline(session)
    uid = await _run_turn(pipe, speaker, held_ms=900)
    source = _events(speaker.ws, "transcript.final")[0]["data"]

    reports = [_e["data"] for _e in _events(listener.ws, "latency.report")]
    assert reports, "a fan-out must report its stage timings"
    report = reports[-1]
    assert report["utterance_id"] == uid
    assert report["segment_id"] == source["segment_id"]
    assert report["start_wall_ms"] == source["start_wall_ms"]
    assert report["duration_ms"] == source["duration_ms"]


@pytest.mark.asyncio
async def test_two_speakers_in_a_row_get_distinguishable_captions(
        session, speaker, listener, no_db, monkeypatch):
    """Back-and-forth: the second turn must not look like a revision of the first."""
    carol = RtParticipant(participant_id=uuid.uuid4(), user_id=uuid.uuid4(),
                          display_name="Aman", speak_lang="hi", hear_lang="hi",
                          audio_mode="original", captions_enabled=True,
                          ws=FakeWs(), connected=True)
    for p in (speaker, carol, listener):
        manager.add_participant(session, p)
    monkeypatch.setattr(P, "ai", FakeAI())
    _fake_translate(monkeypatch)

    pipe = P.MeetingPipeline(session)
    # Aman held a 1.2 s turn and stopped; Beth spoke 300 ms ago. Both are being
    # committed within milliseconds of each other, so arrival order is not
    # speaking order.
    first = await _run_turn(pipe, speaker, held_ms=1200)
    second = await _run_turn(pipe, carol, held_ms=300)

    finals = [_e["data"] for _e in _events(listener.ws, "transcript.final")]
    assert len(finals) == 2
    # Same display name on purpose: identity cannot come from the label.
    assert {f["speaker_id"] for f in finals} == {str(speaker.participant_id),
                                                 str(carol.participant_id)}
    assert {f["utterance_id"] for f in finals} == {first, second}
    # And the timeline says who spoke first, even though both arrive together.
    by_uid = {f["utterance_id"]: f for f in finals}
    assert by_uid[first]["start_wall_ms"] < by_uid[second]["start_wall_ms"]


@pytest.mark.asyncio
async def test_injected_turns_are_on_the_same_timeline(
        session, speaker, listener, no_db, monkeypatch):
    """The dev/golden injection path is what CI exercises, so it must carry the
    same metadata — otherwise the alignment tests would only cover a code path
    nobody ships."""
    manager.add_participant(session, speaker)
    manager.add_participant(session, listener)
    monkeypatch.setattr(P, "ai", FakeAI())
    _fake_translate(monkeypatch)

    pipe = P.MeetingPipeline(session)
    await pipe.inject_transcript(speaker, "नमस्ते", "hi")
    await _drain(pipe)

    final = _events(speaker.ws, "transcript.final")[0]["data"]
    assert final["start_wall_ms"] == pytest.approx(time.time() * 1000, abs=500)
    assert final["utterance_id"]
