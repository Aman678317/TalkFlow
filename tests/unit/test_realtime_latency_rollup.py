"""Phase 4: measure the wait the listener actually experienced.

The guide's performance target is "speech-end to first translated audio", p50 and
p95. That phrasing is the whole task. Every number the realtime path already
reported started at the first audio *frame* of the turn, so a report conflated
two different questions: how long the speaker talked, and how long the pipeline
took to answer once they had stopped. The Prometheus histogram labelled "speech
end -> translated audio delivered" was fed a sum of stage durations that started
at that first frame, so it never measured what its own name says.

So these tests check two things:

 1. where the clock starts — the end of speech, with the VAD's own detection
    pause subtracted, because the silence that ends a turn belongs to the
    speaker and not to us, and crediting ourselves for it is the flattering
    error;
 2. what is sampled and reported — one sample per turn at the first audio byte,
    never per chunk, never a negative or unanchored turn, per language pair, over
    a bounded window, with an unmeasured pair absent rather than zero.

Part 1 drives the real speaker loop with a scripted VAD, because that is the only
place the anchor is decided. Part 2 is pure bookkeeping against the event bus:
providers cannot affect it.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from gt_ai.vad import SpeechEvent, VadState

import app.realtime.pipeline as P
from app.config import settings
from app.realtime.agents.bus import AgentBus
from app.realtime.agents.contracts import RealtimeEvent, Stage
from app.realtime.agents.supervisor import LATENCY_WINDOW, Supervisor, _percentile
from app.realtime.session_manager import RtParticipant, RtSession, manager

MEETING = str(uuid.uuid4())
SPEAKER = str(uuid.uuid4())


class FakeClock:
    def __init__(self) -> None:
        self.now_ms = 1_000_000

    def __call__(self) -> int:
        return self.now_ms

    def advance(self, ms: int) -> None:
        self.now_ms += ms


def _room(**sup_kwargs):
    clock = FakeClock()
    bus = AgentBus(clock=clock)
    sup = Supervisor(clock=clock, meeting_id=MEETING, **sup_kwargs)
    sup.attach(bus)
    return bus, sup, clock


async def _publish(bus: AgentBus, event_type: Stage, *, corr: str = "utt-1",
                   segment: str = "seg-1", **payload) -> None:
    await bus.publish(RealtimeEvent(type=event_type, correlation_id=corr,
                                    meeting_id=MEETING, speaker_id=SPEAKER,
                                    segment_id=segment, payload=payload))


async def _turn(bus: AgentBus, sup: Supervisor, clock: FakeClock, *,
                corr: str = "utt-1", segment: str = "seg-1",
                speech_end_ms: int | None = 0, src: str = "hi", tgt: str = "en",
                chunks: int = 1, step_ms: int = 1_000) -> tuple[int, int]:
    """Publish one complete turn, ticking the fake clock `step_ms` per stage.

    `speech_end_ms` is an absolute wall time and may be None for "the pipeline
    never learned when this turn ended". Returns the turn's first audio frame and
    the arrival of the first translated chunk, so a test can state the arithmetic
    instead of restating it.
    """
    first_frame = clock.now_ms + step_ms
    sup.note_active_segment(SPEAKER, correlation_id=corr, sequence_number=1,
                            target_languages=[tgt],
                            speech_end_wall_ms=speech_end_ms or 0)
    stages = [
        (Stage.AUDIO_CAPTURED, {}),
        (Stage.TRANSCRIPT_FINAL, {"source_language": src}),
        (Stage.TRANSLATION_READY, {"target_language": tgt}),
    ]
    for stage, extra in stages:
        clock.advance(step_ms)
        await _publish(bus, stage, corr=corr, segment=segment, **extra)
    for i in range(chunks):
        clock.advance(step_ms)
        await _publish(bus, Stage.TTS_CHUNK_READY, corr=corr, segment=segment,
                       target_language=tgt, chunk_index=i)
    return first_frame, clock.now_ms


def _pair(sup: Supervisor, pair: str) -> dict:
    return sup.latency_summary()["pairs"][pair]


# --------------------------------------------------------------------------- #
# the percentile itself
# --------------------------------------------------------------------------- #

def test_percentile_is_nearest_rank_not_linear_interpolation():
    """Nearest-rank, because a p95 of 8.4 ms that nobody ever waited is not a
    measurement. The number has to be a turn that actually happened."""
    assert _percentile([100], 0.50) == 100
    assert _percentile([10, 20], 0.50) == 10          # rank 1 of 2
    assert _percentile([10, 20], 0.95) == 20          # rank 2 of 2
    ranks = list(range(1, 101))
    assert _percentile(ranks, 0.50) == 50
    assert _percentile(ranks, 0.95) == 95
    assert _percentile(ranks, 0.99) == 99


def test_percentile_never_indexes_past_the_sample():
    assert _percentile([7], 0.95) == 7
    assert _percentile([1, 2, 3], 1.0) == 3


# --------------------------------------------------------------------------- #
# what gets sampled
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_an_unanchored_turn_is_not_measured():
    """No speech-end means no claim. Reporting zero would say "fast"."""
    bus, sup, clock = _room()
    await _turn(bus, sup, clock, speech_end_ms=None)

    assert sup.latency_summary()["pairs"] == {}


@pytest.mark.asyncio
async def test_the_sample_is_the_gap_from_the_anchor_to_the_first_chunk():
    bus, sup, clock = _room()
    frame, first_chunk = await _turn(bus, sup, clock, speech_end_ms=clock.now_ms)

    assert first_chunk - frame == 3_000
    assert _pair(sup, "hi->en") == {"n": 1, "p50_ms": 4_000, "p95_ms": 4_000,
                                    "max_ms": 4_000}


@pytest.mark.asyncio
async def test_a_longer_turn_does_not_borrow_the_speakers_own_time():
    """The two questions, side by side on one turn. The speaker kept talking for
    six seconds of it; the listener's wait after they stopped is the rest. A
    report that gives only the frame-anchored number answers neither, and the
    gate asks for the second."""
    bus, sup, clock = _room()
    frame, first_chunk = await _turn(bus, sup, clock,
                                     speech_end_ms=clock.now_ms + 11_000,
                                     step_ms=5_000)

    report = sup.segment_report("utt-1")
    assert report["speech_to_first_translated_audio_ms"] == first_chunk - frame
    assert report["speech_end_to_first_audio_ms"] == 9_000
    assert _pair(sup, "hi->en")["p50_ms"] == 9_000


@pytest.mark.asyncio
async def test_one_sample_per_turn_however_many_chunks():
    """The question is when the listener *started* hearing the turn. Sampling
    every chunk would make a long translation dominate the p95 for being long."""
    bus, sup, clock = _room()
    await _turn(bus, sup, clock, speech_end_ms=clock.now_ms)
    for i in range(1, 5):
        clock.advance(300)
        await _publish(bus, Stage.TTS_CHUNK_READY, target_language="en",
                       chunk_index=i)

    assert _pair(sup, "hi->en")["n"] == 1


@pytest.mark.asyncio
async def test_audio_that_predates_the_anchor_is_not_a_wait():
    """A clock jump, or a turn the pipeline never declared ended. Both produce a
    negative gap, and averaging one in would make the meeting look faster than it
    was."""
    bus, sup, clock = _room()
    await _turn(bus, sup, clock, speech_end_ms=clock.now_ms + 20_000)

    assert sup.latency_summary()["pairs"] == {}


@pytest.mark.asyncio
async def test_each_language_pair_is_reported_separately():
    """A Hindi-to-English run and a Hindi-to-Tamil run of the same turn are two
    different waits for two different listeners, and the deployment target is
    stated per pair."""
    bus, sup, clock = _room()
    anchor = clock.now_ms
    await _turn(bus, sup, clock, tgt="en", speech_end_ms=anchor)
    await _turn(bus, sup, clock, corr="utt-2", segment="seg-2", tgt="ta",
                speech_end_ms=anchor)

    pairs = sup.latency_summary()["pairs"]
    assert set(pairs) == {"hi->en", "hi->ta"}
    assert all(p["n"] == 1 for p in pairs.values())


@pytest.mark.asyncio
async def test_a_pair_with_no_audio_never_appears():
    bus, sup, clock = _room()
    await _turn(bus, sup, clock, tgt="en", speech_end_ms=clock.now_ms)

    assert "hi->ta" not in sup.latency_summary()["pairs"]


@pytest.mark.asyncio
async def test_the_overall_row_pools_the_pairs_and_says_how_many():
    bus, sup, clock = _room()
    samples = []
    for i, tgt in enumerate(("en", "en", "ta")):
        step = 100 * (i + 1)
        await _turn(bus, sup, clock, corr=f"utt-{i}", segment=f"seg-{i}", tgt=tgt,
                    speech_end_ms=clock.now_ms, step_ms=step)
        samples.append(4 * step)

    summary = sup.latency_summary()
    assert summary["overall"]["n"] == 3
    assert summary["overall"]["max_ms"] == max(samples)


@pytest.mark.asyncio
async def test_the_window_is_bounded_and_keeps_the_recent_turns():
    """A meeting runs for hours. A p95 over every turn since the room opened
    describes a deployment that no longer exists, and an unbounded list is a
    memory leak with a report attached."""
    bus, sup, clock = _room(latency_window=3)
    for i in range(7):
        await _turn(bus, sup, clock, corr=f"utt-{i}", segment=f"seg-{i}",
                    speech_end_ms=clock.now_ms, step_ms=100 * (i + 1))

    pair = _pair(sup, "hi->en")
    assert pair["n"] == 3, "the window grew past its bound"
    # four stages per turn, so turn i contributed 400*(i+1) ms; the survivors are
    # the last three and the older four are gone.
    assert (pair["p50_ms"], pair["max_ms"]) == (2_400, 2_800)
    assert sup.latency_summary()["window"] == 3


def test_the_default_window_is_the_shipped_one():
    _bus, sup, _clock = _room()
    assert sup.latency_window == LATENCY_WINDOW


# --------------------------------------------------------------------------- #
# the per-turn report keeps both questions answerable
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_a_turn_with_no_anchor_reports_zero_rather_than_a_fabricated_start():
    bus, sup, clock = _room()
    await _turn(bus, sup, clock, speech_end_ms=None)
    report = sup.segment_report("utt-1")

    assert report["speech_end_wall_ms"] == 0
    assert report["speech_end_to_first_audio_ms"] == 0
    assert report["speech_to_first_translated_audio_ms"] > 0


# --------------------------------------------------------------------------- #
# where the anchor comes from: the real speaker loop
# --------------------------------------------------------------------------- #

class ScriptedVad:
    """Returns one scripted event list per ``process()`` call, then nothing."""

    def __init__(self, script: list[list[SpeechEvent]]) -> None:
        self._script = list(script)

    def process(self, _pcm16: bytes) -> list[SpeechEvent]:
        return self._script.pop(0) if self._script else []


@pytest.fixture
def room(monkeypatch):
    @asynccontextmanager
    async def _fake_session(*_a, **_kw):
        yield SimpleNamespace(add=lambda *_: None, commit=lambda: None,
                              execute=lambda *_: None)

    monkeypatch.setattr(P, "db_session", _fake_session)
    session = RtSession(session_id="sess-anchor", meeting_id=uuid.uuid4(),
                        org_id=uuid.uuid4(), room_name="room", mode="ws")
    speaker = RtParticipant(participant_id=uuid.uuid4(), user_id=uuid.uuid4(),
                            display_name="Aman", speak_lang="hi", hear_lang="en",
                            audio_mode="original", captions_enabled=True,
                            ws=SimpleNamespace(events=[], send_text=lambda *_: None,
                                               send_bytes=lambda *_: None),
                            connected=True)
    manager.add_participant(session, speaker)
    return session, speaker


class AnchorRecorder:
    """Stands in for finalization and remembers when each turn ended.

    The loop fires finalization as a task, so the recorder exposes an event a test
    can wait on instead of polling.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[int, bool]] = []
        self.fired = asyncio.Event()

    async def __call__(self, _p, _u, *, forced=False, audio_bytes=b"", start_ms=0,
                       capture_started=None, utterance_id=None, seq=0,
                       end_wall_ms=0) -> None:
        self.calls.append((end_wall_ms, forced))
        self.fired.set()

    @property
    def anchors(self) -> list[int]:
        return [ms for ms, forced in self.calls if not forced]

    async def wait(self, timeout: float = 2.0) -> None:
        try:
            await asyncio.wait_for(self.fired.wait(), timeout)
        except asyncio.TimeoutError:
            pass


def _speech_then_silence() -> ScriptedVad:
    return ScriptedVad([
        [SpeechEvent(state=VadState.SPEECH, timestamp_ms=0, energy=0.05)],
        [SpeechEvent(state=VadState.SILENCE, timestamp_ms=600, energy=0.0)],
    ])


@pytest.mark.asyncio
async def test_a_turn_ended_by_silence_is_anchored_before_the_detection_pause(
        room, monkeypatch):
    """The VAD cannot know the speaker has finished until `vad_min_silence_ms` of
    quiet has passed. Anchoring on that decision would credit the pipeline with
    the speaker's own pause and report every turn that much faster than it felt."""
    session, speaker = room
    monkeypatch.setattr(settings, "vad_min_silence_ms", 500, raising=False)
    monkeypatch.setattr(P, "create_vad", lambda *_a, **_k: _speech_then_silence())
    pipe = P.MeetingPipeline(session)
    rec = AnchorRecorder()
    monkeypatch.setattr(pipe, "_finalize_utterance", rec)

    pipe.start_speaker(speaker)
    try:
        before = int(time.time() * 1000)
        await pipe.feed_audio(speaker.participant_id, b"\x01\x02" * 1600)
        await pipe.feed_audio(speaker.participant_id, b"\x01\x02" * 1600)
        await rec.wait()
    finally:
        pipe.stop_speaker(speaker.participant_id)

    assert rec.anchors, "the turn ended but no speech-anchor reached the pipeline"
    anchor = rec.anchors[0]
    assert anchor <= before + 100, f"the anchor was set {anchor - before} ms late"
    assert before - anchor >= settings.vad_min_silence_ms - 150, (
        f"anchor {anchor} is the VAD's decision time, not the speaker's: the "
        "detection pause was not subtracted")


@pytest.mark.asyncio
async def test_a_forced_split_anchors_at_the_cut_not_before_it(room, monkeypatch):
    """A mid-speech commit has no trailing silence to subtract: this turn's audio
    simply stops being included at this instant, so the anchor is now."""
    session, speaker = room
    monkeypatch.setattr(P, "create_vad", lambda *_a, **_k: ScriptedVad([
        [SpeechEvent(state=VadState.SPEECH, timestamp_ms=0, energy=0.05)],
    ]))
    monkeypatch.setattr(settings, "vad_max_speech_ms", 120, raising=False)
    monkeypatch.setattr(settings, "vad_phrase_commit_ms", 0, raising=False)

    pipe = P.MeetingPipeline(session)
    rec = AnchorRecorder()
    monkeypatch.setattr(pipe, "_finalize_utterance", rec)

    pipe.start_speaker(speaker)
    try:
        for _ in range(40):
            await pipe.feed_audio(speaker.participant_id, b"\x01\x02" * 1600)
            await asyncio.sleep(0.01)
            if rec.anchors:
                break
    finally:
        pipe.stop_speaker(speaker.participant_id)

    assert rec.anchors, "the length cap fired but carried no anchor"
    assert abs(time.time() * 1000 - rec.anchors[0]) < 1_000


@pytest.mark.asyncio
async def test_an_injected_turn_is_anchored_at_arrival(room, monkeypatch):
    """`transcript.inject` has no audio and no VAD, but it is the path the
    benchmark drives. A turn delivered as finished text is complete the instant
    it arrives, so that instant is its speech-end — and without an anchor the
    benchmark would measure nothing at all."""
    session, speaker = room
    pipe = P.MeetingPipeline(session)
    committed: dict = {}

    async def capture(_p, **kwargs):
        committed.update(kwargs)

    monkeypatch.setattr(pipe, "_commit_segment", capture)
    monkeypatch.setattr(P, "ai", SimpleNamespace(is_dev_mode=lambda _task: True))

    before = int(time.time() * 1000)
    await pipe.inject_transcript(speaker, "Hello there", "en")

    assert committed["speech_end_wall_ms"] >= before
