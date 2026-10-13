"""Phase 4 bullet 1: stage events are privacy-safe *and* complete.

The guide asks for "privacy-safe structured stage events; use event IDs, sequence
numbers, stage timings, payload lengths, language codes and sanitized error
codes". Phase 2 built the envelope — `event_id`, a wall clock stamped by the bus,
typed stages, correlation ids — and then filled the payload with
``model_dump(exclude_defaults=False)`` of the whole segment. That made the trace
a second copy of everything anybody said: 4 096 events per meeting holding the
recognised words, the translated words and the word-level timestamps, plus the
raw provider exception text on every failure.

So the requirement is not "add fields", it is "add the fields *without* the
content". Every test here asserts both halves: the metadata a supervisor needs to
reconstruct a turn, and the absence of a single word of what was said.
"""
from __future__ import annotations

import uuid

import pytest
from gt_ai.types import AudioChunk, DetectionResult, RouteDecision, TranscriptChunk

from app.realtime.agents.bus import AgentBus
from app.realtime.agents.contracts import (
    RealtimeEvent,
    Stage,
    TranscriptSegment,
)
from app.realtime.agents.listening import ListeningAgent
from app.realtime.agents.supervisor import Supervisor
from app.realtime.agents.translation import (
    ProviderTranslation,
    TranslationAgent,
)
from app.realtime.agents.voice import VoiceAgent

MEETING = str(uuid.uuid4())
SPEAKER = str(uuid.uuid4())
LISTENER_EN = str(uuid.uuid4())

#: What the speaker said. The target sentence embeds it, so one string checks
#: both languages: if any of these characters reach the trace, the test fails.
SPOKEN = "मुझे एक कप चाय चाहिए कृपया"
TRANSLATED = "I would like a cup of tea please"


class FakeClock:
    """A millisecond clock the test moves. Stage timings are integer wall
    milliseconds, so a real clock makes two fast stages look like zero
    milliseconds apart and any `> 0` assertion becomes a race."""

    def __init__(self, start: int = 1_000_000) -> None:
        self.now_ms = start

    def __call__(self) -> int:
        return self.now_ms

    def advance(self, ms: int) -> None:
        self.now_ms += ms


def _decision(provider: str, task: str) -> RouteDecision:
    return RouteDecision(provider=provider, model=f"{provider}-1", task=task,
                         reason="test-fake")


class FakeStt:
    def __init__(self, error: str = "") -> None:
        self.error = error

    async def transcribe(self, audio: bytes, sample_rate: int,
                         lang_hint: str | None = None):
        if self.error:
            raise RuntimeError(self.error)
        return TranscriptChunk(text=SPOKEN, language="hi", is_final=True,
                               start_ms=0, end_ms=1200, confidence=0.92,
                               model="fake-stt", provider="fake"), _decision("fake", "stt")

    async def detect_language(self, text: str) -> DetectionResult:
        return DetectionResult(language="hi", confidence=0.9, provider="fake")


class FakeTranslator:
    """Echoes the source into the target so one leak check covers both languages."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def translate(self, text: str, source_lang: str, target_lang: str,
                        context: tuple[str, ...] = (), *,
                        segment_id: str | None = None,
                        speaker_id: str | None = None):
        if self.fail:
            raise RuntimeError(f"engine rejected: {text} -> {target_lang}")
        return ProviderTranslation(text=f"{TRANSLATED} {text}", provider="fake",
                                   model="fake-mt", latency_ms=42.0)


class FakeTts:
    async def synthesize_stream(self, text: str, lang: str, voice: str | None = None):
        async def stream():
            for i in range(2):
                yield AudioChunk(data=b"\x00" * (320 * (i + 1)), sample_rate=24000,
                                 encoding="pcm_s16le", format="wav", provider="fake",
                                 model="fake-tts", duration_ms=400.0, is_dev=True)
        return stream(), _decision("fake-tts", "tts")


async def _no_delivery(ready, audio, recipients) -> None:
    return None


def _transcript(seq: int = 7) -> TranscriptSegment:
    return TranscriptSegment(
        correlation_id="utt-1", meeting_id=MEETING, speaker_id=SPEAKER,
        segment_id="seg-1", sequence_number=seq, source_language="hi",
        recognized_text=SPOKEN, start_time_ms=10_000, end_time_ms=11_200,
        is_final=True)


def _trace_text(bus: AgentBus) -> str:
    """Everything the meeting's observation spine knows, as one string."""
    return str([(e.type, e.sequence, e.payload) for e in bus.trace])


# --------------------------------------------------------------------------- #
# the words stay out
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_a_transcript_event_reports_how_much_was_said_not_what():
    bus = AgentBus()
    agent = ListeningAgent(bus, FakeStt(), meeting_id=MEETING)

    await agent.finalize(correlation_id="utt-1", speaker_id=SPEAKER,
                         segment_id="seg-1", sequence_number=7,
                         audio=b"\x01" * 32_000, start_ms=10_000, end_ms=11_200)

    event = bus.trace[-1]
    assert event.type is Stage.TRANSCRIPT_FINAL
    assert "recognized_text" not in event.payload
    assert SPOKEN not in _trace_text(bus)
    # …and the length that replaces it, so a reviewer can still see the turn size
    assert event.payload["text_chars"] == len(SPOKEN)
    assert event.payload["word_count"] == len(SPOKEN.split())


@pytest.mark.asyncio
async def test_word_timestamps_stay_out_of_the_trace():
    """Captions need them; the observation spine does not, and they are the
    recognised words again in a second, more granular form."""
    segment = _transcript().model_copy(update={"word_timestamps": [
        {"word": w, "start_ms": i * 200} for i, w in enumerate(SPOKEN.split())]})
    event = segment.to_event(Stage.TRANSCRIPT_FINAL)
    assert "word_timestamps" not in event.payload
    assert event.payload["word_count"] == len(SPOKEN.split())
    assert SPOKEN.split()[0] not in str(event.model_dump())


@pytest.mark.asyncio
async def test_a_translation_event_carries_lengths_for_both_languages():
    bus = AgentBus()
    agent = TranslationAgent(bus, FakeTranslator(), meeting_id=MEETING)

    await agent.translate_one(_transcript(), "en", [LISTENER_EN])

    event = bus.trace[-1]
    assert event.type is Stage.TRANSLATION_READY
    assert event.payload["source_chars"] == len(SPOKEN)
    assert event.payload["translated_chars"] == len(f"{TRANSLATED} {SPOKEN}")
    assert SPOKEN not in _trace_text(bus)
    assert TRANSLATED not in _trace_text(bus)
    # what a supervisor orders by and a reviewer attributes to is all still there
    assert event.payload["provider"] == "fake"
    assert event.payload["model"] == "fake-mt"
    assert event.payload["latency_ms"] == 42.0
    assert event.payload["target_language"] == "en"


@pytest.mark.asyncio
async def test_a_stage_failure_event_names_the_error_class_not_its_message():
    """Provider error bodies routinely quote the text they were handed, so an
    error string in the trace is a content leak wearing a diagnosis costume."""
    bus = AgentBus()
    agent = TranslationAgent(bus, FakeTranslator(fail=True), meeting_id=MEETING)

    with pytest.raises(RuntimeError):
        await agent.translate_one(_transcript(), "en", [LISTENER_EN])

    event = bus.trace[-1]
    assert event.type is Stage.STAGE_FAILED
    assert event.payload["error_code"] == "RuntimeError"
    assert event.payload["reason"] == "provider_unavailable"
    assert event.payload["recoverable"] is True
    assert "error" not in event.payload
    assert SPOKEN not in _trace_text(bus)


@pytest.mark.asyncio
async def test_sanitising_the_event_does_not_blind_the_operator():
    """The cause still has to reach the person fixing the outage — it travels in
    the failure record the session owner reads, not in the bus payload."""
    bus = AgentBus()
    agent = ListeningAgent(bus, FakeStt(error=f"decode failed on: {SPOKEN}"),
                           meeting_id=MEETING)

    segment = await agent.finalize(correlation_id="utt-1", speaker_id=SPEAKER,
                                   segment_id="seg-1", sequence_number=7,
                                   audio=b"\x01" * 32_000, start_ms=10_000,
                                   end_ms=11_200)
    assert segment is None
    failure = agent.take_failure("utt-1")
    assert failure is not None and failure["error_code"] == "RuntimeError"
    assert "decode failed" in failure["error"]
    assert "error" not in bus.trace[-1].payload
    assert SPOKEN not in _trace_text(bus)


# --------------------------------------------------------------------------- #
# …and the numbering is complete
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_every_event_on_the_bus_gets_a_monotonic_sequence_number():
    bus = AgentBus()
    for i in range(5):
        await bus.publish(RealtimeEvent(type=Stage.AUDIO_CAPTURED,
                                        correlation_id=f"c{i}", meeting_id=MEETING))
    # an event that already carries its own timestamp must still be numbered —
    # the old "copy only if unstamped" branch skipped both at once.
    await bus.publish(RealtimeEvent(type=Stage.AUDIO_CAPTURED, correlation_id="x",
                                    meeting_id=MEETING, timestamp_ms=999))
    assert [e.bus_sequence for e in bus.trace] == [1, 2, 3, 4, 5, 6]
    assert bus.trace[-1].timestamp_ms == 999


@pytest.mark.asyncio
async def test_sequence_numbers_are_per_bus_not_global():
    a, b = AgentBus(), AgentBus()
    await a.publish(RealtimeEvent(type=Stage.INTERRUPT, correlation_id="a",
                                  meeting_id=MEETING))
    await b.publish(RealtimeEvent(type=Stage.INTERRUPT, correlation_id="b",
                                  meeting_id=MEETING))
    await a.publish(RealtimeEvent(type=Stage.INTERRUPT, correlation_id="a2",
                                  meeting_id=MEETING))
    assert [e.bus_sequence for e in a.trace] == [1, 2]
    assert [e.bus_sequence for e in b.trace] == [1]


@pytest.mark.asyncio
async def test_translation_and_chunk_events_carry_the_turn_sequence():
    """`sequence` existed and was left at 0 for every stage after Agent 1, so
    the two stages a listener actually waits on had no turn number at all."""
    bus = AgentBus()
    agent = TranslationAgent(bus, FakeTranslator(), meeting_id=MEETING)
    produced = await agent.translate_one(_transcript(seq=42), "en", [LISTENER_EN])

    assert produced.source_sequence_number == 42
    assert bus.trace[-1].sequence == 42

    voice = VoiceAgent(bus, FakeTts(), meeting_id=MEETING)
    assert await voice.synthesize(produced, recipients=[LISTENER_EN],
                                  deliver=_no_delivery) == 2
    chunks = [e for e in bus.trace if e.type is Stage.TTS_CHUNK_READY]
    assert len(chunks) == 2
    assert all(e.sequence == 42 for e in chunks)
    assert all(e.payload["chunk_index"] == i
               for i, e in enumerate(chunks))


# --------------------------------------------------------------------------- #
# the supervisor loses nothing
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_the_supervisor_reconstructs_a_whole_turn_from_metadata_alone():
    """The regression guard for the whole change: Agent 4 sees only the bus, so
    if the trace stops being enough to supervise a turn, this trade was too
    expensive and must not ship."""
    bus = AgentBus()
    sup = Supervisor(meeting_id=MEETING)
    sup.attach(bus)

    listening = ListeningAgent(bus, FakeStt(), meeting_id=MEETING)
    await listening.on_audio_captured(correlation_id="utt-1", speaker_id=SPEAKER,
                                      segment_id="seg-1", start_ms=10_000,
                                      sequence_number=7, audio_bytes=32_000)
    segment = await listening.finalize(
        correlation_id="utt-1", speaker_id=SPEAKER, segment_id="seg-1",
        sequence_number=7, audio=b"\x01" * 32_000, start_ms=10_000, end_ms=11_200)

    translator = TranslationAgent(bus, FakeTranslator(), meeting_id=MEETING)
    produced = await translator.translate_one(segment, "en", [LISTENER_EN])

    voice = VoiceAgent(bus, FakeTts(), meeting_id=MEETING)
    assert await voice.synthesize(produced, recipients=[LISTENER_EN],
                                  deliver=_no_delivery) == 2

    report = sup.segment_report("utt-1")
    assert {"audio_captured", "transcript_final", "translation_ready",
            "tts_chunk_ready", "audio_delivered"} <= set(report["stages"])
    assert report["source_language"] == "hi"
    assert report["target_language"] == "en"
    assert report["chunks_delivered"] == 2 and report["missing_chunks"] == 0
    assert sup.metrics["stage_failures"] == 0

    # and none of it needed a single word of the sentence
    assert SPOKEN not in _trace_text(bus)


@pytest.mark.asyncio
async def test_stage_timings_survive_the_trace_being_content_free():
    """Agent 4 measures the chain from bus stamps alone. Pinning the numbers
    here is what makes it safe to remove the text: supervision must still be
    possible without it, to the millisecond."""
    clock = FakeClock()
    bus = AgentBus(clock=clock)
    sup = Supervisor(meeting_id=MEETING)
    sup.attach(bus)

    listening = ListeningAgent(bus, FakeStt(), meeting_id=MEETING)
    await listening.on_audio_captured(correlation_id="utt-2", speaker_id=SPEAKER,
                                      segment_id="seg-2", start_ms=10_000,
                                      sequence_number=7, audio_bytes=32_000)
    clock.advance(300)
    segment = await listening.finalize(
        correlation_id="utt-2", speaker_id=SPEAKER, segment_id="seg-2",
        sequence_number=7, audio=b"\x01" * 32_000, start_ms=10_000, end_ms=11_200)
    clock.advance(200)
    produced = await TranslationAgent(bus, FakeTranslator(),
                                      meeting_id=MEETING).translate_one(
        segment, "en", [LISTENER_EN])
    clock.advance(150)
    await VoiceAgent(bus, FakeTts(), meeting_id=MEETING).synthesize(
        produced, recipients=[LISTENER_EN], deliver=_no_delivery)

    report = sup.segment_report("utt-2")
    assert report["stt_ms"] == 300
    assert report["translation_ms"] == 200
    assert report["tts_first_audio_ms"] == 150
    assert report["speech_to_first_translated_audio_ms"] == 650
    assert report["speech_to_delivery_ms"] == 650
