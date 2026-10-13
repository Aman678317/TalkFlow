"""Phase 4: a participant who leaves must not stay in the meeting's memory.

The PDF's Phase 4 bullet this pins is *"ensure health indicators mean the
pipeline stage actually ran"* — answerable only if what a room holds is what the
room is doing *now*. The disconnect handler used to stop the speaker's audio loop
and nothing else: the translation context window (raw transcript text), the
per-speaker sequence ledger, the language record of a turn that failed, and the
in-flight fan-out of a speaker who hung up mid-sentence all stayed behind for the
life of the session. A meeting that runs for hours on a flaky network accumulates
one of each per reconnect.

Evidence level: the real ``MeetingPipeline``, real ``Supervisor``, real agents,
fake providers. ``tests/integration/test_realtime_disconnect.py`` covers the same
release through the real WebSocket handler.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from gt_ai.types import (
    AudioChunk, DetectionResult, RouteDecision, TranscriptChunk, TranslationResult,
)

import app.realtime.pipeline as P
from app.realtime.session_manager import RtParticipant, RtSession, manager


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
    """``unresolved`` stands for audio the recogniser returned words for but no
    language: detection runs, reports, and still cannot name one."""

    def __init__(self, *, unresolved: bool = False, tts_chunks: int = 20) -> None:
        self.unresolved = unresolved
        self.tts_chunks = tts_chunks

    async def transcribe(self, audio: bytes, sample_rate: int,
                         lang_hint: str | None = None):
        if not self.unresolved:
            return (TranscriptChunk(text="नमस्ते", language="hi", is_final=True,
                                    confidence=0.9, model="fake-stt",
                                    provider="fake"),
                    _decision("fake-stt", "stt"))
        return (TranscriptChunk(text="ᱚᱛᱚᱦᱚ", language=None, is_final=True,
                                confidence=0.2, model="fake-stt", provider="fake"),
                _decision("fake-stt", "stt"))

    async def detect_language(self, text: str) -> DetectionResult:
        return DetectionResult(language="auto", confidence=0.4,
                               provider="fake-detect")

    async def synthesize_stream(self, text: str, lang: str, voice: str | None = None):
        n = self.tts_chunks

        async def stream():
            for _ in range(n):
                await asyncio.sleep(0)      # yield, so a cancel can land mid-run
                yield AudioChunk(data=b"\x54\x48" * 80, sample_rate=24000,
                                 encoding="pcm_s16le", format="wav",
                                 provider="fake-tts", model="fake-tts-m",
                                 duration_ms=250.0)
        return stream(), _decision("fake-tts", "tts")

    def is_dev_mode(self, task) -> bool:
        return True


def _participant(*, hear: str, speak: str = "hi", name: str = "p") -> RtParticipant:
    return RtParticipant(participant_id=uuid.uuid4(), user_id=uuid.uuid4(),
                         display_name=name, speak_lang=speak, hear_lang=hear,
                         audio_mode="translated", captions_enabled=True,
                         ws=FakeWs(), connected=True)


@pytest.fixture
def session():
    return RtSession(session_id="sess-release", meeting_id=uuid.uuid4(),
                     org_id=uuid.uuid4(), room_name="room", mode="ws")


@pytest.fixture
def no_db(monkeypatch):
    @asynccontextmanager
    async def _fake_session(*_a, **_kw):
        yield SimpleNamespace(add=lambda *_: None, commit=lambda: None,
                              execute=lambda *_: None)
    monkeypatch.setattr(P, "db_session", _fake_session)


@pytest.fixture
def fake_mt(monkeypatch):
    async def fake_translate(db, text, src, tgt, ctx):
        return SimpleNamespace(result=TranslationResult(
            text=f"[{tgt}] {text}", source_lang=src, target_lang=tgt,
            model="fake-mt", provider="fake-mt", latency_ms=5.0, quality_flags=[]))

    monkeypatch.setattr(P, "translate_text", fake_translate)


def _join(session: RtSession, *participants: RtParticipant) -> None:
    for p in participants:
        manager.add_participant(session, p)


def _events(ws: FakeWs, event_type: str) -> list[dict]:
    return [e for e in ws.events if e.get("type") == event_type]


def _diags(ws: FakeWs, stage: str) -> list[dict]:
    return [e["data"] for e in _events(ws, "diagnostic") if e["data"].get("stage") == stage]


async def _fan_out(pipe: P.MeetingPipeline, speaker: RtParticipant, *, seq: int,
                   corr: str, targets: set[str]) -> None:
    pipe._start_fanout(speaker=speaker, segment_id=uuid.uuid4(), seq=seq,
                       utterance_id=corr, text="नमस्ते", source_lang="hi",
                       targets=targets, stt_ms=1.0, capture_ms=1.0, prev_context=())


def _block_correlation(monkeypatch, pipe: P.MeetingPipeline,
                       correlation_id: str) -> asyncio.Event:
    release = asyncio.Event()
    real = pipe._translate_and_synthesize

    async def maybe_block(**kwargs):
        if kwargs.get("utterance_id") == correlation_id:
            await release.wait()
        else:
            await real(**kwargs)

    monkeypatch.setattr(pipe, "_translate_and_synthesize", maybe_block)
    return release


async def _wait_for(predicate, what: str, timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            pytest.fail(f"timed out waiting for {what}")
        await asyncio.sleep(0.005)


# --------------------------------------------------------------------------- #
# Per-speaker bookkeeping
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_a_departed_speaker_leaves_nothing_keyed_to_them(session, monkeypatch):
    """The context window is the entry that matters: it holds the speaker's own
    words, in memory, for a meeting they are no longer in."""
    monkeypatch.setattr(P, "ai", FakeAI())
    a = _participant(hear="en", name="Aman")
    _join(session, a)
    pipe = P.MeetingPipeline(session)
    pipe.start_speaker(a)
    pipe.translating.note_source(str(a.participant_id), "नमस्ते")
    pipe._latest_final_seq[a.participant_id] = 3

    pipe.release_participant(a.participant_id)

    assert pipe.translating._context == {}, "their transcript text stayed behind"
    assert pipe._latest_final_seq == {}
    assert pipe.speaker_tasks == {} and pipe.audio_queues == {}
    assert pipe.vads == {} and pipe.utterances == {}
    await pipe.shutdown()


def test_releasing_the_same_participant_twice_is_not_an_event(session, monkeypatch):
    """A socket closing races with an explicit REST leave. The second caller must
    find nothing to do rather than cancel somebody else's turn."""
    monkeypatch.setattr(P, "ai", FakeAI())
    a, b = _participant(hear="en", name="Aman"), _participant(hear="en", name="Beth")
    _join(session, a, b)
    pipe = P.MeetingPipeline(session)
    pipe.translating.note_source(str(b.participant_id), "धन्यवाद")
    pipe._latest_final_seq[b.participant_id] = 7

    pipe.release_participant(a.participant_id)
    pipe.release_participant(a.participant_id)
    pipe.release_participant(uuid.uuid4())

    assert list(pipe.translating._context) == [str(b.participant_id)]
    assert pipe._latest_final_seq == {b.participant_id: 7}


# --------------------------------------------------------------------------- #
# In-flight work
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_releasing_a_speaker_stops_their_run_and_leaves_nobody_elses_alone(
        session, no_db, fake_mt, monkeypatch):
    """A hang-up is an interruption with no new speech behind it: audio for a
    turn its speaker abandoned must stop being produced, and the other person in
    the room is entitled to every chunk of their own."""
    monkeypatch.setattr(P, "ai", FakeAI())
    a, b = _participant(hear="hi", name="Aman"), _participant(hear="hi", name="Beth")
    en = _participant(hear="en", name="Chen")
    _join(session, a, b, en)
    pipe = P.MeetingPipeline(session)
    corr_a, corr_b = str(uuid.uuid4()), str(uuid.uuid4())
    release = _block_correlation(monkeypatch, pipe, corr_a)

    await _fan_out(pipe, a, seq=1, corr=corr_a, targets={"en"})
    await _fan_out(pipe, b, seq=1, corr=corr_b, targets={"en"})
    task_a = pipe.translation_tasks[(str(a.participant_id), 1, "en")]
    task_b = pipe.translation_tasks[(str(b.participant_id), 1, "en")]

    pipe.release_participant(a.participant_id)

    assert task_a.cancelled() or task_a.cancelling()
    assert not task_b.cancelled() and not task_b.cancelling()
    assert corr_a not in pipe._fanout_pending
    assert corr_a not in pipe.supervisor._active
    assert pipe.supervisor.is_cancelled(corr_a), "a late chunk could still be played"
    await _wait_for(
        lambda: str(a.participant_id) not in {k[0] for k in pipe.translation_tasks},
        "the abandoned run to be released from the task table")

    release.set()
    await _wait_for(lambda: _events(en.ws, "tts.chunk"), "Beth's audio to deliver")
    await pipe.shutdown()


@pytest.mark.asyncio
async def test_releasing_a_speaker_drops_their_agent_state_not_just_the_task(
        session, no_db, fake_mt, monkeypatch):
    """Cancellation alone leaks: the voice agent still holds that run's dedup
    keys, so a chunk 0 replayed by a speaker who rejoined is judged a duplicate
    of audio nobody heard."""
    monkeypatch.setattr(P, "ai", FakeAI(tts_chunks=20))
    a = _participant(hear="hi", name="Aman")
    en = _participant(hear="en", name="Chen")
    _join(session, a, en)
    pipe = P.MeetingPipeline(session)
    corr = str(uuid.uuid4())
    await _fan_out(pipe, a, seq=1, corr=corr, targets={"en"})

    while not _events(en.ws, "tts.chunk"):
        await asyncio.sleep(0)
    pipe.release_participant(a.participant_id)
    await asyncio.sleep(0.05)

    assert [k for k in pipe.voice._seen if k[0] == corr] == []
    assert [k for k in pipe.voice._deliveries if k[0] == corr] == []
    await pipe.shutdown()


@pytest.mark.asyncio
async def test_a_departed_listener_loses_their_stale_language_marks(session,
                                                                     monkeypatch):
    """`participant_id` is per join, so every reconnect of someone who changed
    language left another (id, language) pair in the stale set forever."""
    monkeypatch.setattr(P, "ai", FakeAI())
    a = _participant(hear="en", name="Aman")
    _join(session, a)
    pipe = P.MeetingPipeline(session)

    await pipe.supervisor.recipient_changed(str(a.participant_id),
                                            previous_language="en",
                                            new_language="hi")
    assert (str(a.participant_id), "en") in pipe.supervisor._stale_recipients

    pipe.release_participant(a.participant_id)
    assert pipe.supervisor._stale_recipients == set()


# --------------------------------------------------------------------------- #
# A turn that failed after detection
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_a_turn_with_no_language_releases_the_language_it_tried_to_find(
        session, monkeypatch):
    """Detection runs *inside* the transcript stage and reports to the meeting
    before the stage decides it cannot name a language. The consumer of that
    report is the caption that never arrives here — so the record has to be
    released on this path too, not only on the one that succeeds."""
    monkeypatch.setattr(P, "ai", FakeAI(unresolved=True))
    a = _participant(hear="en", name="Aman", speak="auto")
    _join(session, a)
    pipe = P.MeetingPipeline(session)
    corr = str(uuid.uuid4())
    u = P.UtteranceState(participant_id=a.participant_id, seq=1, capture_started=0.0)

    await pipe._finalize_utterance(a, u, audio_bytes=b"\x01\x02" * 1600,
                                  start_ms=0, utterance_id=uuid.UUID(corr), seq=1,
                                  end_wall_ms=0)
    await asyncio.sleep(0.05)

    assert pipe._detected == {}, "the detection outlived the turn it described"
    failed = _diags(a.ws, "stt_failed")
    assert failed, "an unresolved language was not reported to the room"
    assert failed[-1]["reason"] == "unsupported_language"
