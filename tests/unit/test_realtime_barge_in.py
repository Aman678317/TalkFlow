"""Phase 3 — barge-in must cancel one speaker's stale output, nobody else's.

The PDF's Phase 3 requirement is explicit: *"stop or cancel stale queued output
for the interrupted speaker without canceling another speaker's audio"*. The
Phase 2 build shipped a ``Supervisor`` that could do exactly this (``interrupt``
/ ``is_cancelled`` / ``note_active_segment`` / ``prune``) — but nothing called
it, so a speaker who cut themselves off kept listening to their own stale
translated audio on top of the new turn.

These tests drive the real ``MeetingPipeline`` fan-out and the real
``SessionManager`` routing with fake providers, and assert the wire protocol the
browser depends on.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from gt_ai.types import (
    AudioChunk, DetectionResult, RouteDecision, TranscriptChunk, TranslationResult,
)
from gt_ai.vad import SpeechEvent, VadState

import app.realtime.pipeline as P
from app.realtime.agents.contracts import TranslationSegment
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
    def __init__(self, tts_chunks: int = 2) -> None:
        self.tts_chunks = tts_chunks
        self.synthesize_calls: list[str] = []

    async def transcribe(self, audio: bytes, sample_rate: int,
                         lang_hint: str | None = None):
        return (TranscriptChunk(text="नमस्ते", language="hi", is_final=True,
                                confidence=0.9, model="fake-stt", provider="fake"),
                _decision("fake-stt", "stt"))

    async def detect_language(self, text: str) -> DetectionResult:
        return DetectionResult(language="hi", confidence=0.88, provider="fake-detect")

    async def synthesize_stream(self, text: str, lang: str, voice: str | None = None):
        self.synthesize_calls.append(lang)
        n = self.tts_chunks

        async def stream():
            for _i in range(n):
                await asyncio.sleep(0)      # yield, so a cancel can land mid-run
                yield AudioChunk(data=b"\x54\x48" * 80, sample_rate=24000,
                                 encoding="pcm_s16le", format="wav", provider="fake-tts",
                                 model="fake-tts-m", duration_ms=250.0)
        return stream(), _decision("fake-tts", "tts")

    def is_dev_mode(self, task) -> bool:
        return True


def _participant(*, hear: str, mode: str = "translated", speak: str = "auto",
                 captions: bool = True) -> RtParticipant:
    return RtParticipant(participant_id=uuid.uuid4(), user_id=uuid.uuid4(),
                         display_name=f"p-{hear}", speak_lang=speak, hear_lang=hear,
                         audio_mode=mode, captions_enabled=captions,
                         ws=FakeWs(), connected=True)


@pytest.fixture
def session():
    return RtSession(session_id="sess-1", meeting_id=uuid.uuid4(),
                     org_id=uuid.uuid4(), room_name="room", mode="ws")


@pytest.fixture
def no_db(monkeypatch):
    """Fan-out must not need a database to be tested."""
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


def _join(session: RtSession, *participants: RtParticipant) -> None:
    for p in participants:
        manager.add_participant(session, p)


def _events(ws: FakeWs, event_type: str) -> list[dict]:
    return [e for e in ws.events if e.get("type") == event_type]


def _played(ws: FakeWs) -> int:
    """Chunks on both transports — the client dedups them into one play queue."""
    return len(_events(ws, "tts.chunk")) + len(ws.frames)


def _fake_translate(monkeypatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    async def fake_translate(db, text, src, tgt, ctx):
        calls.append((src, tgt))
        return SimpleNamespace(result=TranslationResult(
            text=f"[{tgt}] {text}", source_lang=src, target_lang=tgt,
            model="fake-mt", provider="fake-mt", latency_ms=5.0, quality_flags=[]))

    monkeypatch.setattr(P, "translate_text", fake_translate)
    return calls


async def _hang_factory() -> None:
    await asyncio.Event().wait()


async def _wait_for(predicate, what: str, timeout: float = 2.0) -> None:
    """Fan-out is genuinely concurrent, so a test that asserts delivery has to
    wait for it rather than guess how many loop ticks a provider chain needs."""
    deadline = time.perf_counter() + timeout
    while not predicate():
        if time.perf_counter() > deadline:
            pytest.fail(f"timed out waiting for {what}")
        await asyncio.sleep(0.005)


async def _fan_out(pipe: P.MeetingPipeline, speaker: RtParticipant, *, seq: int,
                   corr: str, targets: set[str],
                   segment_id: uuid.UUID) -> str:
    """Launch one segment's fan-out exactly as ``_commit_segment`` does, and
    return the correlation the browser would have to be told to drop."""
    pipe._start_fanout(speaker=speaker, segment_id=segment_id, seq=seq,
                       utterance_id=corr, text="नमस्ते", source_lang="hi",
                       targets=targets, stt_ms=1.0, capture_ms=1.0, prev_context=())
    return corr


def _block_fanout(monkeypatch, pipe: P.MeetingPipeline) -> asyncio.Event:
    """Hold every language run mid-flight so cancellation has something to cut."""
    release = asyncio.Event()

    async def hang(*_a, **_kw):
        await release.wait()

    monkeypatch.setattr(pipe, "_translate_and_synthesize", hang)
    return release


def _block_correlation(monkeypatch, pipe: P.MeetingPipeline,
                       correlation_id: str) -> asyncio.Event:
    """Block one turn's language runs and let the rest of the meeting proceed,
    so a test can prove an interruption is scoped in time as well as by speaker."""
    release = asyncio.Event()
    real = pipe._translate_and_synthesize

    async def maybe_block(**kwargs):
        if kwargs.get("utterance_id") == correlation_id:
            await release.wait()
        else:
            await real(**kwargs)

    monkeypatch.setattr(pipe, "_translate_and_synthesize", maybe_block)
    return release


# --------------------------------------------------------------------------- #
# The fan-out has to be *trackable*: per speaker, per correlation
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_fan_out_registers_the_correlation_as_active_for_that_speaker(
        session, speaker, no_db, monkeypatch):
    """Without this the supervisor has nothing to cancel — which is exactly how
    barge-in stayed unwired. ``interrupt()`` matches on speaker, so the
    bookkeeping has to know whose output is in flight."""
    en = _participant(hear="en")
    _join(session, speaker, en)
    monkeypatch.setattr(P, "ai", FakeAI())
    _fake_translate(monkeypatch)
    pipe = P.MeetingPipeline(session)
    corr = str(uuid.uuid4())

    await _fan_out(pipe, speaker, seq=1, corr=corr, targets={"en"},
                   segment_id=uuid.uuid4())

    active = pipe.supervisor._active[corr]
    assert active["speaker_id"] == str(speaker.participant_id)
    assert active["target_languages"] == ["en"]
    await _wait_for(lambda: _events(en.ws, "tts.chunk"), "chunk delivery")


@pytest.mark.asyncio
async def test_two_speakers_at_the_same_sequence_do_not_share_a_task_slot(
        session, no_db, monkeypatch):
    """``translation_tasks`` used to be keyed ``(seq, target_lang)``. ``seq`` is a
    per-speaker counter, so two speakers both on turn 1 translated to English
    overwrote each other's entry — and the loser could never be cancelled."""
    a, b = _participant(hear="hi"), _participant(hear="hi")
    en = _participant(hear="en")
    _join(session, a, b, en)
    monkeypatch.setattr(P, "ai", FakeAI())
    _fake_translate(monkeypatch)
    pipe = P.MeetingPipeline(session)
    release = _block_fanout(monkeypatch, pipe)

    corr_a, corr_b = str(uuid.uuid4()), str(uuid.uuid4())
    await _fan_out(pipe, a, seq=1, corr=corr_a, targets={"en"}, segment_id=uuid.uuid4())
    await _fan_out(pipe, b, seq=1, corr=corr_b, targets={"en"}, segment_id=uuid.uuid4())

    assert len(pipe.translation_tasks) == 2
    assert {key[0] for key in pipe.translation_tasks} == {str(a.participant_id),
                                                          str(b.participant_id)}
    release.set()


# --------------------------------------------------------------------------- #
# Barge-in: cancel the right things, tell the browser, leave others alone
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_barge_in_cancels_the_interrupting_speakers_output_only(
        session, no_db, monkeypatch):
    a, b = _participant(hear="hi"), _participant(hear="hi")
    en = _participant(hear="en")
    _join(session, a, b, en)
    monkeypatch.setattr(P, "ai", FakeAI())
    _fake_translate(monkeypatch)
    pipe = P.MeetingPipeline(session)
    release = _block_fanout(monkeypatch, pipe)

    corr_a, corr_b = str(uuid.uuid4()), str(uuid.uuid4())
    await _fan_out(pipe, a, seq=1, corr=corr_a, targets={"en"}, segment_id=uuid.uuid4())
    await _fan_out(pipe, b, seq=1, corr=corr_b, targets={"en"}, segment_id=uuid.uuid4())
    task_a = pipe.translation_tasks[(str(a.participant_id), 1, "en")]
    task_b = pipe.translation_tasks[(str(b.participant_id), 1, "en")]

    cancelled = await pipe._handle_barge_in(a)
    await asyncio.sleep(0)

    assert cancelled == [corr_a]
    assert task_a.cancelled() or task_a.cancelling()
    assert not task_b.cancelled() and not task_b.cancelling()
    assert pipe.supervisor.is_cancelled(corr_a)
    assert not pipe.supervisor.is_cancelled(corr_b)
    assert corr_a not in pipe.supervisor._active
    assert corr_b in pipe.supervisor._active
    release.set()


@pytest.mark.asyncio
async def test_barge_in_stops_a_synthesis_that_is_already_streaming(
        session, no_db, monkeypatch):
    """Cancellation must bite mid-stream, not only before it starts: the point of
    barge-in is that the stale half-sentence stops talking over the new one."""
    a = _participant(hear="hi")
    en = _participant(hear="en")
    _join(session, a, en)
    monkeypatch.setattr(P, "ai", FakeAI(tts_chunks=20))
    _fake_translate(monkeypatch)
    pipe = P.MeetingPipeline(session)
    corr = str(uuid.uuid4())

    pipe.supervisor.note_active_segment(str(a.participant_id), correlation_id=corr,
                                        sequence_number=1, target_languages=["en"])
    task = asyncio.create_task(pipe._translate_and_synthesize(
        segment_id=uuid.uuid4(), seq=1, speaker=a, text="नमस्ते", source_lang="hi",
        target_lang="en", stt_ms=1.0, capture_ms=1.0, utterance_id=corr))

    while not _events(en.ws, "tts.chunk"):
        await asyncio.sleep(0)

    await pipe._handle_barge_in(a)
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)
    await asyncio.sleep(0.05)

    assert 0 < _played(en.ws) < 40, f"the full 20-chunk run streamed anyway: {_played(en.ws)}"


@pytest.mark.asyncio
async def test_barge_in_emits_one_scoped_playback_flush(session, no_db, monkeypatch):
    """The browser's queue is the thing that actually talks over the speaker, so
    the drop has to be declared on the wire — and scoped, or one speaker's
    interruption silences everybody else's queued audio."""
    a, b = _participant(hear="hi"), _participant(hear="hi")
    en, ur = _participant(hear="en"), _participant(hear="ur")
    _join(session, a, b, en, ur)
    monkeypatch.setattr(P, "ai", FakeAI())
    _fake_translate(monkeypatch)
    pipe = P.MeetingPipeline(session)
    corr = str(uuid.uuid4())

    await _fan_out(pipe, a, seq=2, corr=corr, targets={"en", "ur"},
                   segment_id=uuid.uuid4())

    await pipe._handle_barge_in(b)                      # B has nothing in flight
    assert _events(en.ws, "playback.flush") == []

    await pipe._handle_barge_in(a)
    flushes = _events(en.ws, "playback.flush")
    assert len(flushes) == 1
    flush = flushes[0]
    assert flush["speaker_id"] == str(a.participant_id)
    assert flush["reason"] == "barge_in"
    assert flush["scope"] == "speaker"
    assert flush["recoverable"] is True
    # every listener is told, whatever language they listen in
    assert len(_events(ur.ws, "playback.flush")) == 1


@pytest.mark.asyncio
async def test_playback_flush_is_sequenced_so_resume_cannot_lose_it(
        session, no_db, monkeypatch):
    """A client that reconnects mid-interruption replays from the resume buffer.
    An unsequenced flush would be absent from that buffer, and the browser would
    play the stale audio it was told to drop."""
    a = _participant(hear="hi")
    en = _participant(hear="en")
    _join(session, a, en)
    monkeypatch.setattr(P, "ai", FakeAI())
    _fake_translate(monkeypatch)
    pipe = P.MeetingPipeline(session)
    corr = str(uuid.uuid4())
    await _fan_out(pipe, a, seq=1, corr=corr, targets={"en"}, segment_id=uuid.uuid4())
    await pipe._handle_barge_in(a)

    flushed = [raw for raw in session.replay_buffer
               if json.loads(raw).get("type") == "playback.flush"]
    assert flushed
    assert json.loads(flushed[-1])["sequence"] > 0


@pytest.mark.asyncio
async def test_a_cancelled_correlation_is_stale_even_at_the_current_sequence(
        session, no_db, monkeypatch):
    """The old staleness rule only fired once a *newer final* existed, which is
    too late for barge-in: the interrupted speaker's next turn has not been
    transcribed yet, so seq-based staleness still says "current"."""
    a = _participant(hear="hi")
    monkeypatch.setattr(P, "ai", FakeAI())
    _fake_translate(monkeypatch)
    pipe = P.MeetingPipeline(session)
    corr = str(uuid.uuid4())
    pipe._latest_final_seq[a.participant_id] = 1

    assert pipe._is_stale(a.participant_id, 1, corr) is False
    pipe.supervisor.note_active_segment(str(a.participant_id), correlation_id=corr,
                                        sequence_number=1, target_languages=["en"])
    await pipe.supervisor.interrupt(str(a.participant_id), reason="barge_in")
    assert pipe._is_stale(a.participant_id, 1, corr) is True
    # the seq-only callers keep behaving exactly as before
    assert pipe._is_stale(a.participant_id, 1) is False


@pytest.mark.asyncio
async def test_translation_for_a_cancelled_correlation_never_reaches_a_provider(
        session, no_db, monkeypatch):
    a = _participant(hear="hi")
    en = _participant(hear="en")
    _join(session, a, en)
    monkeypatch.setattr(P, "ai", FakeAI())
    calls = _fake_translate(monkeypatch)
    pipe = P.MeetingPipeline(session)
    corr = str(uuid.uuid4())
    pipe.supervisor.note_active_segment(str(a.participant_id), correlation_id=corr,
                                        sequence_number=1, target_languages=["en"])
    await pipe.supervisor.interrupt(str(a.participant_id), reason="barge_in")

    await pipe._translate_and_synthesize(
        segment_id=uuid.uuid4(), seq=1, speaker=a, text="नमस्ते", source_lang="hi",
        target_lang="en", stt_ms=1.0, capture_ms=1.0, utterance_id=corr)

    assert calls == []
    assert en.ws.events == []
    assert en.ws.frames == []


@pytest.mark.asyncio
async def test_another_speakers_segment_still_delivers_after_a_barge_in(
        session, no_db, monkeypatch):
    """The regression this guards: cancellation keyed on the utterance alone (or
    a global flush) silences the person who was *not* interrupted."""
    a, b = _participant(hear="hi"), _participant(hear="hi")
    en = _participant(hear="en")
    _join(session, a, b, en)
    monkeypatch.setattr(P, "ai", FakeAI(tts_chunks=2))
    _fake_translate(monkeypatch)
    pipe = P.MeetingPipeline(session)
    corr_a, corr_b = str(uuid.uuid4()), str(uuid.uuid4())

    pipe.supervisor.note_active_segment(str(a.participant_id), correlation_id=corr_a,
                                        sequence_number=1, target_languages=["en"])
    await pipe._handle_barge_in(a)

    await pipe._translate_and_synthesize(
        segment_id=uuid.uuid4(), seq=1, speaker=b, text="धन्यवाद", source_lang="hi",
        target_lang="en", stt_ms=1.0, capture_ms=1.0, utterance_id=corr_b)

    assert len(_events(en.ws, "tts.chunk")) == 2
    assert len(en.ws.frames) == 2
    assert _events(en.ws, "tts.completed")[-1]["chunks"] == 2
    assert _events(en.ws, "playback.flush")[0]["speaker_id"] == str(a.participant_id)


@pytest.mark.asyncio
async def test_one_language_being_cancelled_does_not_condemn_the_other(
        session, no_db, monkeypatch):
    """Barge-in cancels the speaker's turn, which is in flight for two languages
    at once. Both must be dropped, and the *next* turn in those same languages
    must still be deliverable — the interruption must not leave the two language
    runs permanently marked stale."""
    a = _participant(hear="hi")
    en, ur = _participant(hear="en"), _participant(hear="ur")
    _join(session, a, en, ur)
    monkeypatch.setattr(P, "ai", FakeAI(tts_chunks=2))
    _fake_translate(monkeypatch)
    pipe = P.MeetingPipeline(session)
    corr = str(uuid.uuid4())
    release = _block_correlation(monkeypatch, pipe, corr)

    await _fan_out(pipe, a, seq=1, corr=corr, targets={"en", "ur"},
                   segment_id=uuid.uuid4())
    await pipe._handle_barge_in(a)
    release.set()
    assert _events(ur.ws, "playback.flush")[0]["target_languages"] == ["en", "ur"]

    next_corr = str(uuid.uuid4())
    await _fan_out(pipe, a, seq=2, corr=next_corr, targets={"en", "ur"},
                   segment_id=uuid.uuid4())
    # Wait on the audio, not on the caption events: `tts.chunk` and its binary
    # frame are one pair in the writer's queue, so an event-only wait can see the
    # second event in the moment before the second frame is handed to the socket.
    await _wait_for(lambda: len(en.ws.frames) >= 2 and len(ur.ws.frames) >= 2,
                   "the speaker's next turn to deliver audio")
    assert len(_events(en.ws, "tts.chunk")) >= 2
    assert len(_events(ur.ws, "tts.chunk")) >= 2


# --------------------------------------------------------------------------- #
# Wiring: the speaker loop must actually trigger it
# --------------------------------------------------------------------------- #

class ScriptedVad:
    """Emits a prepared list of event lists, one per processed chunk."""

    def __init__(self, script: list) -> None:
        self._script = list(script)
        self.clock_ms = 0

    def process(self, _pcm16: bytes) -> list:
        return self._script.pop(0) if self._script else []


@pytest.mark.asyncio
async def test_new_speech_from_a_speaker_triggers_barge_in_in_the_speaker_loop(
        session, no_db, monkeypatch):
    """A supervisor nobody calls is not a feature. The trigger is VAD speech
    onset, so this drives the real ``_speaker_loop``."""
    a = _participant(hear="hi")
    en = _participant(hear="en")
    _join(session, a, en)
    monkeypatch.setattr(P, "ai", FakeAI())
    _fake_translate(monkeypatch)

    corr = str(uuid.uuid4())
    pipe = P.MeetingPipeline(session)

    def make_vad(_provider, **_kw):
        return ScriptedVad([[SpeechEvent(state=VadState.SPEECH, timestamp_ms=100,
                                         energy=0.05)]])

    monkeypatch.setattr(P, "create_vad", make_vad)
    pipe.start_speaker(a)
    pipe.supervisor.note_active_segment(str(a.participant_id), correlation_id=corr,
                                        sequence_number=1, target_languages=["en"])
    task = asyncio.create_task(_hang_factory())
    pipe.translation_tasks[(str(a.participant_id), 1, "en")] = task

    await pipe.feed_audio(a.participant_id, b"\x01\x02" * 800)
    for _ in range(100):
        if _events(en.ws, "playback.flush"):
            break
        await asyncio.sleep(0.01)

    assert pipe.supervisor.is_cancelled(corr)
    assert _events(en.ws, "playback.flush")
    assert _events(en.ws, "speech.started")
    assert task.cancelled() or task.cancelling()
    await pipe.shutdown()


@pytest.mark.asyncio
async def test_barge_in_releases_the_interrupted_run_from_agent_state(
        session, no_db, monkeypatch):
    """Two leaks make an interruption worse than the interruption itself: the
    voice agent's dedup/delivery rows for the dead run survive if only the task
    is cancelled, so the *next* attempt at chunk 0 is judged a duplicate and is
    never played."""
    a = _participant(hear="hi")
    en = _participant(hear="en")
    _join(session, a, en)
    monkeypatch.setattr(P, "ai", FakeAI(tts_chunks=20))
    _fake_translate(monkeypatch)
    pipe = P.MeetingPipeline(session)
    corr, segment_id = str(uuid.uuid4()), uuid.uuid4()

    pipe.supervisor.note_active_segment(str(a.participant_id), correlation_id=corr,
                                        sequence_number=1, target_languages=["en"])
    task = asyncio.create_task(pipe._translate_and_synthesize(
        segment_id=segment_id, seq=1, speaker=a, text="नमस्ते", source_lang="hi",
        target_lang="en", stt_ms=1.0, capture_ms=1.0, utterance_id=corr))
    while not _events(en.ws, "tts.chunk"):
        await asyncio.sleep(0)

    await pipe._handle_barge_in(a)
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)

    assert corr not in pipe.supervisor._active
    assert [k for k in pipe.voice._seen if k[0] == corr] == []
    assert [k for k in pipe.voice._deliveries if k[0] == corr] == []

    delivered_before = _played(en.ws)
    assert delivered_before >= 1

    replayed: list[int] = []

    async def record(ready, audio, _recipients) -> None:
        replayed.append(ready.chunk_index)

    delivered = await pipe.voice.publish_chunk(
        TranslationSegment(correlation_id=corr, meeting_id=pipe._meeting_id,
                           speaker_id=str(a.participant_id), recipient_id="*",
                           source_segment_id=str(segment_id), source_language="hi",
                           target_language="en", translated_text="Hello"),
        index=0, audio=b"fake-wav", duration_ms=10, sample_rate=24000, codec="wav",
        recipients=[], deliver=record)

    assert delivered is True, "the retried chunk was suppressed as a duplicate"
    assert replayed == [0]
    assert _played(en.ws) == delivered_before
