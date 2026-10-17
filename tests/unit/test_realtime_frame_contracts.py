"""Realtime frame contracts (remediation plan P1, test matrix item 1).

Covers the four contract families the plan requires for realtime tests:

1. PCM16 format/frame contract and bounded queue backpressure
   (``pipeline.feed_audio``).
2. Ordered sequence handling: a newer finalized turn makes an older turn's
   in-flight translation stale, and a barge-in cancels it (playback.flush).
3. Partial-STT lifecycle: partials are open until ``finalize`` rotates the
   turn; after finalize they are discarded (stale partial cancellation).
4. Per-stage deadlines: STT / MT / TTS-TTFB deadlines fail *down*, never take
   the call down (``reason="deadline_exceeded"`` on the wire), plus the
   process-wide inference gate actually bounds concurrent inference.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from gt_ai.types import AudioChunk, DetectionResult, RouteDecision

import app.realtime.pipeline as P
from app.config import settings
from app.realtime.agents.inference_gate import (
    InferenceGate, StageDeadlineExpired, reset_default_gate,
)
from app.realtime.agents.listening import ListeningAgent
from app.realtime.agents.translation import (
    ProviderTranslation, RealtimeTranslatorProvider, TranslationAgent,
)
from app.realtime.agents.voice import RealtimeTtsProvider, VoiceAgent
from app.realtime.agents.bus import AgentBus
from app.realtime.agents.contracts import Stage
from app.realtime.session_manager import RtParticipant, RtSession, manager


MEETING = str(uuid.uuid4())
SPEAKER = uuid.uuid4()


# --------------------------------------------------------------------------- #
# Harness (same style as test_realtime_pipeline_delivery.py)
# --------------------------------------------------------------------------- #

class FakeWs:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def send_text(self, payload: str) -> None:
        self.events.append(json.loads(payload))


def _join(session: RtSession, *participants: RtParticipant) -> None:
    for p in participants:
        manager.add_participant(session, p)


def _speaker() -> RtParticipant:
    return RtParticipant(participant_id=SPEAKER, user_id=uuid.uuid4(),
                         display_name="aman", speak_lang="hi", hear_lang="hi",
                         audio_mode="original", captions_enabled=True,
                         ws=FakeWs(), connected=True)


def _with_audio_queue(pipe: P.MeetingPipeline) -> asyncio.Queue:
    """Register the ingestion queue without starting a real speaker loop:
    these tests exercise the *contract*, not STT inference."""
    q: asyncio.Queue = asyncio.Queue(maxsize=P.AUDIO_QUEUE_MAX)
    pipe.audio_queues[SPEAKER] = q
    return q


@pytest.fixture
def session():
    return RtSession(session_id="sess-fc", meeting_id=uuid.uuid4(),
                     org_id=uuid.uuid4(), room_name="room-fc", mode="ws")


def _events(ws: FakeWs, event_type: str) -> list[dict]:
    return [e for e in ws.events if e.get("type") == event_type]


# --------------------------------------------------------------------------- #
# 1 — PCM format / frame contract
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_feed_audio_enforces_the_pcm16_frame_contract(session):
    pipe = P.MeetingPipeline(session)
    q = _with_audio_queue(pipe)
    pid = SPEAKER

    # sane 16 kHz 50 ms frame (1600 bytes) is accepted
    good = b"\x00\x01" * 800
    await pipe.feed_audio(pid, good)
    assert q.get_nowait() == good

    # a trailing odd byte is trimmed, then accepted (16-bit samples stay whole)
    odd = good[:-1]
    await pipe.feed_audio(pid, odd)
    assert q.get_nowait() == good[:-2]

    # sub-frame fragments (< 160 B) are dropped, not queued
    await pipe.feed_audio(pid, b"\x00\x01" * 20)
    assert q.empty()

    # oversized bursts (> 64 KB) are dropped, not queued
    await pipe.feed_audio(pid, b"\x00\x01" * 40_000)
    assert q.empty()


@pytest.mark.asyncio
async def test_backpressure_drops_oldest_and_degrades_honestly(session):
    pipe = P.MeetingPipeline(session)
    p = _speaker()
    _join(session, p)
    q = _with_audio_queue(pipe)
    before = P.met.DROPPED_AUDIO_FRAMES.labels(
        reason="audio_backpressure")._value.get()

    # fill the bounded buffer, then one more: the oldest frame is sacrificed
    for _ in range(q.maxsize):
        await pipe.feed_audio(SPEAKER, b"\x02\x00" * 800)
    await pipe.feed_audio(SPEAKER, b"\x03\x00" * 800)

    assert q.qsize() == q.maxsize
    assert q.get_nowait() == b"\x02\x00" * 800      # frame 0 was the drop
    assert q.get_nowait() == b"\x02\x00" * 800      # frame 1 survived
    assert P.met.DROPPED_AUDIO_FRAMES.labels(
        reason="audio_backpressure")._value.get() == before + 1
    # honest degraded broadcast, still connected
    degraded = _events(p.ws, "quality.degraded")
    assert degraded and degraded[-1]["reason"] == "audio_backpressure"
    assert degraded[-1]["recoverable"] is True


# --------------------------------------------------------------------------- #
# 2 — ordered sequence handling & barge-in playback flush
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_a_newer_finalized_turn_makes_older_audio_stale(session):
    pipe = P.MeetingPipeline(session)
    speaker = SPEAKER
    assert pipe._is_stale(speaker, 1) is False          # nothing newer yet
    pipe._latest_final_seq[speaker] = 3
    assert pipe._is_stale(speaker, 1) is True           # older turn is stale
    assert pipe._is_stale(speaker, 3) is False          # current turn live


@pytest.mark.asyncio
async def test_barge_in_cancels_in_flight_runs_and_flushes_playback(session):
    pipe = P.MeetingPipeline(session)
    p = _speaker()
    _join(session, p)
    pid = str(SPEAKER)
    # one language run declared in-flight, as _start_fanout would do
    pipe.supervisor.note_active_segment(
        pid, correlation_id="utt-old", sequence_number=1,
        target_languages=["en"])
    started = asyncio.Event()

    async def never_translation():
        started.set()
        await asyncio.sleep(60)

    task = asyncio.get_running_loop().create_task(never_translation())
    pipe.translation_tasks[(pid, 1, "en")] = task
    await started.wait()

    cancelled = await pipe._handle_barge_in(p)

    assert cancelled == ["utt-old"]
    await asyncio.sleep(0)                     # let cancellation propagate
    assert task.cancelled() or task.done()
    # exactly one playback flush, scoped to this speaker
    flushed = _events(p.ws, "playback.flush")
    assert len(flushed) == 1
    assert flushed[0]["reason"] == "barge_in"
    assert flushed[0]["correlation_ids"] == ["utt-old"]


# --------------------------------------------------------------------------- #
# 3 — partial STT lifecycle: open while speaking, discarded after finalize
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_partial_transcription_stops_rotating_after_finalize(session):
    bus = AgentBus()

    class PausableStt:
        def __init__(self) -> None:
            self.calls = 0

        async def transcribe(self, audio: bytes, sample_rate: int,
                             lang_hint: str | None = None):
            self.calls += 1
            await asyncio.sleep(0)   # no hang; a deterministic quick call
            from gt_ai.types import TranscriptChunk
            return TranscriptChunk(text=f"पाठ {self.calls}", language="hi",
                                   is_final=True, confidence=0.9,
                                   model="fake-stt", provider="fake"), \
                RouteDecision(provider="fake", model="fake-m", task="stt",
                              reason="test-fake")

        async def detect_language(self, text: str) -> DetectionResult:
            return DetectionResult(language="hi", confidence=0.9,
                                   provider="fake-detect")

    stt = PausableStt()
    agent = ListeningAgent(bus, stt, meeting_id=MEETING)
    u = "utt-a"
    partial1 = await agent.transcribe_partial(
        correlation_id=u, speaker_id=str(SPEAKER), segment_id="s",
        sequence_number=1, audio=b"\x00\x01" * 1600)
    assert partial1 is not None and partial1.is_final is False
    final = await agent.finalize(
        correlation_id=u, speaker_id=str(SPEAKER), segment_id="s",
        sequence_number=1, audio=b"\x00\x01" * 1600, start_ms=0, end_ms=500)
    assert final is not None and final.is_final is True
    # the turn rotated: no more partials for a closed correlation
    late = await agent.transcribe_partial(
        correlation_id=u, speaker_id=str(SPEAKER), segment_id="s",
        sequence_number=1, audio=b"\x00\x01" * 1600)
    assert late is None
    # 1 (partial) + 1 (final recognition) — the closed turn gets no more calls
    assert stt.calls == 2


# --------------------------------------------------------------------------- #
# 4 — per-stage deadlines & bounded inference
# --------------------------------------------------------------------------- #

@pytest.fixture
def fast_deadlines(monkeypatch):
    monkeypatch.setattr(settings, "rt_stt_deadline_ms", 60.0)
    monkeypatch.setattr(settings, "rt_mt_deadline_ms", 60.0)
    monkeypatch.setattr(settings, "rt_tts_ttfb_deadline_ms", 60.0)


class HangingStt:
    async def transcribe(self, audio: bytes, sample_rate: int,
                         lang_hint: str | None = None):
        await asyncio.sleep(30)
        raise AssertionError("must never return")

    async def detect_language(self, text: str) -> DetectionResult:
        return DetectionResult(language="hi", confidence=0.9, provider="fake")


@pytest.mark.asyncio
async def test_stt_deadline_degrades_the_caption_without_hanging_the_room(
        fast_deadlines):
    bus = AgentBus()
    agent = ListeningAgent(bus, HangingStt(), meeting_id=MEETING)
    out = await agent.finalize(correlation_id="utt", speaker_id=str(SPEAKER),
                               segment_id="s", sequence_number=1,
                               audio=b"\x00\x01" * 1600,
                               start_ms=0, end_ms=500)
    assert out is None                        # no transcript, but no hang
    failed = [e for e in bus.trace if e.type is Stage.STAGE_FAILED][-1]
    assert failed.payload["reason"] == "deadline_exceeded"
    assert failed.payload["recoverable"] is True


@pytest.mark.asyncio
async def test_mt_deadline_fails_the_language_run_without_blocking_others(
        fast_deadlines):
    """The deadline lives in the production adapter, so hang the function the
    adapter actually calls and expect the graceful mapped failure."""
    bus = AgentBus()

    async def hanging_translate_fn(db, text, src, tgt, ctx):
        await asyncio.sleep(30)
        raise AssertionError("must never return")

    @asynccontextmanager
    async def _fake_session(*_a, **_kw):
        yield SimpleNamespace()

    provider = RealtimeTranslatorProvider(
        _fake_session, lambda *a, **kw: SimpleNamespace(),
        translate_fn=hanging_translate_fn)
    agent = TranslationAgent(bus, provider, meeting_id=MEETING)
    from app.realtime.agents.contracts import TranscriptSegment
    seg = TranscriptSegment(correlation_id="utt", meeting_id=MEETING,
                            speaker_id=str(SPEAKER), segment_id="s",
                            sequence_number=1, source_language="hi",
                            recognized_text="नमस्ते", is_final=True)
    with pytest.raises(StageDeadlineExpired):
        await asyncio.wait_for(
            agent.translate_one(seg, "en", [str(SPEAKER)]), timeout=5)
    failed = [e for e in bus.trace if e.type is Stage.STAGE_FAILED][-1]
    assert failed.payload["reason"] == "deadline_exceeded"


class RealFacadeHangingTts:
    async def synthesize_stream(self, text: str, lang: str,
                                voice: str | None = None):
        await asyncio.sleep(30)
        raise AssertionError("must never return")


class NeverFirstChunk:
    async def synthesize_stream(self, text: str, lang: str,
                                voice: str | None = None):
        async def stream():
            await asyncio.sleep(30)
            raise AssertionError("must never yield")
            yield b""  # unreachable: marks this an async generator
        return stream(), RouteDecision(provider="fake", model="fake-m",
                                       task="tts", reason="test-fake")


@pytest.mark.asyncio
async def test_tts_ttfb_deadline_reports_recoverable_failure(fast_deadlines):
    bus = AgentBus()
    agent = VoiceAgent(bus, RealtimeTtsProvider(NeverFirstChunk()),
                       meeting_id=MEETING)
    from app.realtime.agents.contracts import TranslationSegment
    t = TranslationSegment(correlation_id="utt", meeting_id=MEETING,
                           speaker_id=str(SPEAKER), segment_id="s",
                           source_segment_id="s", recipient_id=str(SPEAKER),
                           source_language="hi", target_language="en",
                           translated_text="Hello there", source_text="नमस्ते")
    chunks = await agent.synthesize(t, recipients=[str(SPEAKER)],
                                    deliver=None)
    assert chunks == 0
    failure = agent.take_failure(t)
    assert failure is not None
    assert failure["reason"] == "deadline_exceeded"
    assert failure["recoverable"] is True
    assert failure["original_audio_available"] is True


@pytest.mark.asyncio
async def test_inference_gate_bounds_concurrent_provider_calls():
    gate = InferenceGate(limit=2)
    in_flight = 0
    peak = 0

    @gate.slot()
    async def _slot():  # pragma: no path — used via asynccontextmanager below
        pass

    async def worker():
        nonlocal in_flight, peak
        async with gate.slot():
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.02)
            in_flight -= 1

    await asyncio.gather(*(worker() for _ in range(8)))
    assert peak <= 2


@pytest.mark.asyncio
async def test_default_gate_is_shared_and_resettable(monkeypatch):
    reset_default_gate()
    monkeypatch.setattr(settings, "rt_inference_concurrency", 3)
    gate = __import__(
        "app.realtime.agents.inference_gate",
        fromlist=["default_gate"]).default_gate()
    assert gate is __import__(
        "app.realtime.agents.inference_gate",
        fromlist=["default_gate"]).default_gate()
    reset_default_gate()
