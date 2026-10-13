"""Phase 3 exit gate, as one runnable check on the real conversation path.

The gate in the implementation guide is four clauses, and each one is a claim
about a different component, so each is tested here against the *composed* path
— the real ``MeetingPipeline``, the real ``SessionManager`` routing, the real
wire protocol, four real agents — with only the providers replaced:

  "back-and-forth speech works"                     -> test_back_and_forth
  "interruptions do not create stale/duplicated output"
                                                    -> test_interruption_leaves_no_stale_or_duplicate_output
  "captions align"                                  -> test_captions_align_across_the_exchange
  "and test latency is reported"                    -> test_latency_is_reported_for_every_language_run

Evidence level: integration. It does not prove a human liked what they heard —
that is the listening check, and it needs a real browser with two microphones.
Providers are fakes, so the millisecond numbers this test *prints* are the
pipeline's overhead, not a production translation's latency.
"""
from __future__ import annotations

import asyncio
import json
import statistics
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
from app.realtime.agents.contracts import Stage
from app.realtime.session_manager import RtParticipant, RtSession, manager

SAMPLE_TEXT = {"hi": "नमस्ते, आज हम योजना पर चर्चा करेंगे।",
               "en": "Let us review the plan today."}
# 800 ms of 16 kHz mono PCM16.
AUDIO = b"\x01\x02" * 12_800
AUDIO_MS = len(AUDIO) / 32.0


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
                         reason="phase3-gate")


class FakeAI:
    """Answers with whatever language the speaker's own setting hints at, so one
    room can hold both a Hindi turn and an English turn."""

    def __init__(self, tts_chunks: int = 3, chunk_delay: float = 0.0) -> None:
        self.tts_chunks = tts_chunks
        self.chunk_delay = chunk_delay

    async def transcribe(self, audio: bytes, sample_rate: int,
                         lang_hint: str | None = None):
        lang = lang_hint or "hi"
        return (TranscriptChunk(text=SAMPLE_TEXT[lang], language=lang, is_final=True,
                                confidence=0.9, model="fake-stt", provider="fake"),
                _decision("fake-stt", "stt"))

    async def detect_language(self, text: str) -> DetectionResult:
        lang = "en" if text[:1].isascii() and text.isascii() else "hi"
        return DetectionResult(language=lang, confidence=0.88, provider="fake-detect")

    async def synthesize_stream(self, text: str, lang: str, voice: str | None = None):
        async def stream():
            for _ in range(self.tts_chunks):
                await asyncio.sleep(self.chunk_delay)
                yield AudioChunk(data=b"\x54\x48" * 80, sample_rate=24000,
                                 encoding="pcm_s16le", format="wav",
                                 provider="fake-tts", model="fake-tts-m",
                                 duration_ms=250.0)
        return stream(), _decision("fake-tts", "tts")

    def is_dev_mode(self, task) -> bool:
        return True


def _participant(*, name: str, speak: str, hear: str,
                 mode: str = "translated") -> RtParticipant:
    return RtParticipant(participant_id=uuid.uuid4(), user_id=uuid.uuid4(),
                         display_name=name, speak_lang=speak, hear_lang=hear,
                         audio_mode=mode, captions_enabled=True,
                         ws=FakeWs(), connected=True)


@pytest.fixture
def no_db(monkeypatch):
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
    monkeypatch.setattr(settings, "retention_audio_days", 0, raising=False)


@pytest.fixture
def room(monkeypatch, no_db):
    """Two Hindi/English speakers and one listener each way.

    Nobody gets a translation of their own turn, so every language group here
    exists because somebody *else* asked for it.
    """
    # The agents capture this instance at construction, so a test that wants a
    # slower or longer stream changes the object, not the module attribute.
    fake_ai = FakeAI()
    monkeypatch.setattr(P, "ai", fake_ai)

    async def fake_translate(db, text, src, tgt, ctx):
        return SimpleNamespace(result=TranslationResult(
            text=f"[{tgt}] {text}", source_lang=src, target_lang=tgt,
            model="fake-mt", provider="fake-mt", latency_ms=5.0, quality_flags=[]))

    monkeypatch.setattr(P, "translate_text", fake_translate)

    session = RtSession(session_id="sess-gate", meeting_id=uuid.uuid4(),
                        org_id=uuid.uuid4(), room_name="room", mode="ws")
    aman = _participant(name="Aman", speak="hi", hear="en")
    beth = _participant(name="Beth", speak="en", hear="hi")
    chen = _participant(name="Chen", speak="ta", hear="en")
    divya = _participant(name="Divya", speak="ur", hear="hi")
    for p in (aman, beth, chen, divya):
        manager.add_participant(session, p)
    return SimpleNamespace(session=session, pipe=P.MeetingPipeline(session),
                           ai=fake_ai, aman=aman, beth=beth, chen=chen, divya=divya)


def _events(ws: FakeWs, event_type: str) -> list[dict]:
    return [e for e in ws.events if e.get("type") == event_type]


def _translated(ws: FakeWs, target_lang: str) -> list[dict]:
    """Translation events for one language.

    `translation.final` is broadcast to the whole room — a listener sees other
    people's translations arrive, they are just not the caption they read.
    """
    return [e for e in _events(ws, "translation.final")
            if e.get("target_language") == target_lang]


def _chunks(ws: FakeWs) -> int:
    return len(_events(ws, "tts.chunk")) + len(ws.frames)


def _runs(pipe: P.MeetingPipeline) -> dict[tuple[str, str], list[int]]:
    """Every TTS chunk the supervisor saw, grouped by (turn, target language).

    Ordering claims are read here rather than from ``segment_report``: the
    supervisor releases a turn's record as soon as its fan-out comes home,
    because a meeting runs for hours and ordering state is bounded per meeting.
    What a *finished* turn leaves behind is the bus trace plus the room-wide
    counters, which is also what an operator sees.
    """
    runs: dict[tuple[str, str], list[int]] = {}
    for e in pipe.bus.trace:
        if e.type is Stage.TTS_CHUNK_READY:
            key = (e.correlation_id, e.payload.get("target_language") or "")
            runs.setdefault(key, []).append(e.payload["chunk_index"])
    return runs


async def _drain(pipe: P.MeetingPipeline) -> None:
    deadline = time.time() + 20.0
    while pipe.translation_tasks and time.time() < deadline:
        await asyncio.gather(*list(pipe.translation_tasks.values()),
                             return_exceptions=True)
    assert not pipe.translation_tasks, "fan-out never came home"


async def _speak(room, speaker: RtParticipant, *, seq: int,
                 held_ms: int = 700) -> str:
    """One complete turn, through the path a microphone drives.

    `held_ms` is how long the speaker talked, and the anchor is when they
    stopped — which for this harness is the moment the turn is handed over. The
    distinction is the Phase 4 measurement: a listener's wait starts at the
    anchor, not at the turn's first frame.
    """
    u = P.UtteranceState(
        participant_id=speaker.participant_id,
        capture_started=time.perf_counter() - held_ms / 1000.0,
        started_at_ms=0, seq=seq, in_speech=False)
    utterance_id = uuid.uuid4()
    await room.pipe._finalize_utterance(
        speaker, u, audio_bytes=AUDIO, start_ms=0,
        capture_started=u.capture_started, utterance_id=utterance_id, seq=seq,
        end_wall_ms=int(time.time() * 1000))
    await _drain(room.pipe)
    return str(utterance_id)


async def _wait_for(predicate, what: str, timeout: float = 5.0) -> None:
    deadline = time.perf_counter() + timeout
    while not predicate():
        if time.perf_counter() > deadline:
            pytest.fail(f"timed out waiting for {what}")
        await asyncio.sleep(0.005)


# --------------------------------------------------------------------------- #
# "back-and-forth speech works"
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_back_and_forth(room):
    aman_turn = await _speak(room, room.aman, seq=1)
    beth_turn = await _speak(room, room.beth, seq=1)

    # Aman spoke Hindi: Chen, who hears English, gets the English voice.
    assert _chunks(room.chen.ws) == 6, "Chen did not hear Aman's turn"
    # Beth spoke English: Divya, who hears Hindi, gets the Hindi voice.
    assert _chunks(room.divya.ws) == 6, "Divya did not hear Beth's turn"

    # Nobody hears their own turn translated back at them.
    assert _chunks(room.aman.ws) == 0
    assert _chunks(room.beth.ws) == 0
    # Each listener's own caption language is the one they asked for, and it
    # exists only because somebody else needed it.
    assert {t["utterance_id"] for t in _translated(room.divya.ws, "hi")} == {beth_turn}
    assert {t["utterance_id"] for t in _translated(room.chen.ws, "en")} == {aman_turn}

    # Both directions are complete, ordered chains: three declared chunks each,
    # arriving 0,1,2, with nothing late, duplicated, or missing.
    assert _runs(room.pipe) == {
        (aman_turn, "en"): [0, 1, 2], (beth_turn, "hi"): [0, 1, 2]}
    metrics = room.pipe.supervisor.metrics
    assert metrics["duplicate_chunks"] == 0
    assert metrics["reordered_chunks"] == 0
    assert metrics["late_chunks"] == 0
    assert metrics["missing_chunks"] == 0
    assert metrics["stage_failures"] == 0
    assert metrics["segments_completed"] == 2


# --------------------------------------------------------------------------- #
# "interruptions do not create stale/duplicated output"
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_interruption_leaves_no_stale_or_duplicate_output(room):
    pipe = room.pipe
    await _speak(room, room.aman, seq=1)            # a turn Chen heard in full
    heard_before = _chunks(room.chen.ws)
    json_before = len(_events(room.chen.ws, "tts.chunk"))

    # A long turn, streaming slowly enough to interrupt mid-flight.
    room.ai.tts_chunks, room.ai.chunk_delay = 30, 0.02
    interrupted = await _start(room, room.aman, seq=2)
    # Wait for a chunk of *this* turn, not for `tts.chunk` to exist — the first
    # turn already filled Chen's socket with three of them.
    await _wait_for(lambda: len(_events(room.chen.ws, "tts.chunk")) > json_before,
                    "a chunk of the interrupted turn")
    stopped_at = len(_events(room.chen.ws, "tts.chunk"))

    await pipe._handle_barge_in(room.aman)          # Aman cuts himself off
    await _drain(pipe)

    assert len(_events(room.chen.ws, "playback.flush")) == 1
    flush = _events(room.chen.ws, "playback.flush")[0]
    assert flush["scope"] == "speaker"
    assert flush["speaker_id"] == str(room.aman.participant_id)
    assert flush["correlation_ids"] == [interrupted]
    # Stale output stops where the interruption happened...
    assert len(_events(room.chen.ws, "tts.chunk")) == stopped_at
    # ...and nothing is played twice: the interrupted run never published a
    # completion, so Chen holds exactly one — the turn he already heard in full
    # (3 declared chunks on each of the two transports).
    assert heard_before == 6
    assert len(_events(room.chen.ws, "tts.completed")) == 1

    # The next turn is delivered in full, in order, in the same language, and
    # the interrupted one left no queue behind: no retry, no gap, no duplicate.
    room.ai.tts_chunks, room.ai.chunk_delay = 3, 0.0
    next_turn = await _speak(room, room.aman, seq=3)
    runs = _runs(pipe)
    assert runs[(next_turn, "en")] == [0, 1, 2]
    stale_run = runs[(interrupted, "en")]
    assert stale_run == list(range(len(stale_run))), "gap or repeat in the cancelled run"
    assert len(stale_run) < 30, "the cancelled run kept synthesizing"
    assert pipe.supervisor.metrics["duplicate_chunks"] == 0
    assert pipe.supervisor.metrics["reordered_chunks"] == 0
    assert pipe._fanout_pending == {}
    assert len(_events(room.chen.ws, "tts.completed")) == 2


async def _start(room, speaker: RtParticipant, *, seq: int) -> str:
    """Launch a turn's fan-out without waiting for it, as a real interruption does."""
    pipe = room.pipe
    utterance_id = uuid.uuid4()
    segment_id = uuid.uuid4()
    pipe._start_fanout(speaker=speaker, segment_id=segment_id, seq=seq,
                       utterance_id=str(utterance_id), text=SAMPLE_TEXT[speaker.speak_lang],
                       source_lang=speaker.speak_lang,
                       targets=manager.required_target_languages(
                           room.session, speaker.speak_lang,
                           exclude_speaker=str(speaker.participant_id)),
                       stt_ms=1.0, capture_ms=1.0, prev_context=())
    return str(utterance_id)


# --------------------------------------------------------------------------- #
# "captions align"
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_captions_align_across_the_exchange(room):
    aman_turn = await _speak(room, room.aman, seq=1, held_ms=1200)
    beth_turn = await _speak(room, room.beth, seq=1, held_ms=300)

    # Every participant sees both source captions, each naming its own turn.
    finals = _events(room.chen.ws, "transcript.final")
    assert {f["utterance_id"] for f in finals} == {aman_turn, beth_turn}
    assert {f["language"] for f in finals} == {"hi", "en"}

    by_turn = {f["utterance_id"]: f for f in finals}
    # Aman talked for 1.2 s and stopped; Beth spoke 300 ms ago. Both arrive here
    # within milliseconds, so arrival order is not speaking order — the caption
    # timeline has to come from the measured turn, and it has to be consistent
    # across the source caption and the translation of it.
    assert by_turn[aman_turn]["start_wall_ms"] < by_turn[beth_turn]["start_wall_ms"]
    assert by_turn[aman_turn]["duration_ms"] == round(AUDIO_MS)
    assert abs(by_turn[aman_turn]["start_wall_ms"]
               - (time.time() * 1000 - 1200)) < 400

    translated = _translated(room.chen.ws, "en")
    assert {t["utterance_id"] for t in translated} == {aman_turn}
    source = by_turn[aman_turn]
    joined = translated[0]
    assert joined["segment_id"] == source["segment_id"]
    assert joined["seq"] == source["seq"]
    assert joined["start_wall_ms"] == source["start_wall_ms"]
    assert joined["duration_ms"] == source["duration_ms"]
    assert joined["target_language"] == room.chen.hear_lang


# --------------------------------------------------------------------------- #
# "test latency is reported"
# --------------------------------------------------------------------------- #

_STAGES = ["audio_capture_ms", "stt_final_ms", "translation_ms",
           "tts_first_audio_ms", "delivery_ms", "total_e2e_latency_ms"]
#: The two the Phase 4 gate names as the measurement of a listener's wait.
_SPEECH_END_STAGES = ["speech_end_to_first_audio_ms", "speech_end_to_delivery_ms"]


@pytest.mark.asyncio
async def test_latency_is_reported_for_every_language_run(room):
    await _speak(room, room.aman, seq=1)
    await _speak(room, room.beth, seq=1)

    reports = _events(room.chen.ws, "latency.report")
    by_turn: dict[str, dict] = {}
    for r in reports:
        by_turn[f"{r['utterance_id']}:{r['target_lang']}"] = r

    # One report per (turn, target language) that was actually run.
    assert len(by_turn) == 2, sorted(by_turn)
    for r in by_turn.values():
        assert r["segment_id"] and r["seq"] >= 1
        assert r["start_wall_ms"] > 0 and r["duration_ms"] > 0
        assert r["total_e2e_latency_ms"] > 0
        assert r["stale_dropped"] is False
        for stage in _STAGES:
            assert r[stage] >= 0
        # Phase 4: the turn has an anchor, and the headline total is measured
        # from it. The old total was a sum of stage durations that started at
        # the turn's first audio frame, so it grew with how long the speaker
        # talked — a number about the meeting, labelled as a number about us.
        assert r["speech_end_wall_ms"] > 0
        for stage in _SPEECH_END_STAGES:
            assert r[stage] > 0, f"{stage} was not measured"
        assert r["total_e2e_latency_ms"] == r["speech_end_to_delivery_ms"]
        assert (r["speech_end_to_first_audio_ms"]
                <= r["speech_end_to_delivery_ms"])

    # The gate asks for the numbers, not just a green tick. These are the
    # pipeline's own overhead against fake providers — the providers' share is
    # measured separately (tests/realtime, CI golden call with real weights).
    print()
    print("phase 3 gate — measured per-stage latency (ms, fake providers)")
    for stage in _STAGES + _SPEECH_END_STAGES:
        vals = [float(r[stage]) for r in by_turn.values()]
        print(f"  {stage:32s} mean {statistics.mean(vals):8.1f}  "
              f"max {max(vals):8.1f}")


@pytest.mark.asyncio
async def test_the_meeting_reports_p50_and_p95_of_the_listeners_wait(room):
    """Phase 4 asks for percentiles, not a sample per turn, and it asks for them
    where an operator can read them: the same health payload that says which
    stages ran.

    A provider-free harness cannot produce a meaningful percentile *value*, so
    what is asserted here is that the rollup exists, is keyed per language pair,
    counts every measured turn, and refuses to invent a row for a pair that
    produced no audio.
    """
    for seq in range(1, 4):
        await _speak(room, room.aman, seq=seq)

    latency = room.pipe.stage_health()["latency"]
    assert latency["window"] > 0
    # Aman speaks Hindi and Chen hears English.
    assert set(latency["pairs"]) == {"hi->en"}, (
        f"expected one language pair, got {sorted(latency['pairs'])}")
    row = latency["pairs"]["hi->en"]
    assert row["n"] == 3, "a measured turn was missing from the percentile"
    assert row["p50_ms"] <= row["p95_ms"] <= row["max_ms"]
    assert latency["overall"]["n"] == 3

    # A pair nobody listened to has no row: a zero would read as a fast meeting.
    assert "hi->ta" not in latency["pairs"]


@pytest.mark.asyncio
async def test_the_injected_turn_is_keyed_by_its_language_pair_too(room):
    """`transcript.inject` is the path the benchmark and the dev console drive.

    It stands in for Agent 1, so it owes Agent 1's bus contract: without a
    transcript stage event the supervisor cannot name the source language, and
    the operator's rollup reads `unknown->en` — which does not answer the guide's
    question, "what is the p95 for this language pair". Observed in a live run.
    """
    await room.pipe.inject_transcript(room.aman,
                                      "नमस्ते, आज हम योजना पर चर्चा करेंगे।", "hi")
    await _drain(room.pipe)

    latency = room.pipe.stage_health()["latency"]
    assert set(latency["pairs"]) == {"hi->en"}, (
        f"the injected turn was keyed {sorted(latency['pairs'])}")
    assert latency["pairs"]["hi->en"]["n"] == 1


@pytest.mark.asyncio
async def test_injected_turns_accumulate_one_sample_each(room):
    """Three turns in two source languages, because a percentile is a count
    before it is a number: the live run reported `n=1` for twelve turns and the
    single-turn test above could not see it.

    Aman's Hindi goes only to Chen (Beth and Divya hear Hindi, so Hindi is their
    own source language and not a translation). His Marathi turn is a translation
    for all three listeners, and it counts once per *pair* — an English caption
    and a Hindi caption are two different waits, and averaging them into one row
    would hide whichever one is slow.
    """
    for text, lang in (("नमस्ते, आज हम योजना पर चर्चा करेंगे।", "hi"),
                       ("आमची बैठक उद्या सकाळी आहे.", "mr"),
                       ("दोनऱ्याची गोष्ट.", "hi")):
        await room.pipe.inject_transcript(room.aman, text, lang)
        await _drain(room.pipe)

    latency = room.pipe.stage_health()["latency"]
    assert {p: row["n"] for p, row in latency["pairs"].items()} == {
        "hi->en": 2, "mr->en": 1, "mr->hi": 1}
    assert latency["overall"]["n"] == 4


@pytest.mark.asyncio
async def test_an_unmeasured_meeting_reports_no_percentiles(room):
    """Before a single turn, the rollup has to be empty rather than zero. The
    Phase 4 gate is a number an operator is judged on; the honest answer to
    "what is your p95" when nothing has run is "nothing has run"."""
    latency = room.pipe.stage_health()["latency"]

    assert latency["pairs"] == {}
    assert "overall" not in latency
