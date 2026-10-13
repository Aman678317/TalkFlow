"""Phase 2 exit gate: run every agent stage against FAKE providers and assert
the complete event trace — no external APIs, no database, no network.

Each test pins one responsibility boundary from the implementation guide
sections 4-5:

  Agent 1  audio ingestion / VAD / STT  -> stable TranscriptSegment
  Agent 2  contextual translation       -> one MT call per distinct target language
  Agent 3  TTS chunks + delivery        -> declares codec/rate/channels/chunk index
  Agent 4  orchestration                -> ordering, duplicates, cancellation, metrics

plus the two cross-cutting rules: raw audio never enters the event bus, and the
event envelope is versioned and typed.
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
    TranslationSegment,
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
LISTENER_EN_1 = str(uuid.uuid4())
LISTENER_EN_2 = str(uuid.uuid4())
LISTENER_UR = str(uuid.uuid4())

HINDI = "नमस्ते, आप कैसे हैं?"


class FakeClock:
    """Deterministic millisecond clock, so timing metrics are assertable."""

    def __init__(self, start: int = 1_000_000) -> None:
        self.now_ms = start

    def __call__(self) -> int:
        return self.now_ms

    def advance(self, ms: int) -> None:
        self.now_ms += ms


def _decision(provider: str, task: str) -> RouteDecision:
    return RouteDecision(provider=provider, model=f"{provider}-1", task=task,
                         reason="test-fake")


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #

class FakeStt:
    def __init__(self, text: str = HINDI, language: str = "hi") -> None:
        self.text = text
        self.language = language
        self.calls: list[tuple[int, str | None]] = []

    async def transcribe(self, audio: bytes, sample_rate: int,
                         lang_hint: str | None = None):
        self.calls.append((len(audio), lang_hint))
        return TranscriptChunk(text=self.text, language=self.language, is_final=True,
                               start_ms=0, end_ms=1200, confidence=0.92,
                               model="fake-stt", provider="fake"), _decision("fake", "stt")

    async def detect_language(self, text: str) -> DetectionResult:
        return DetectionResult(language=self.language, confidence=0.9,
                               provider="fake")


class RaisingStt:
    async def transcribe(self, audio, sample_rate, lang_hint=None):
        raise TimeoutError("stt timed out")

    async def detect_language(self, text):
        return DetectionResult(language="auto", confidence=0.0, provider="fake")


class FakeTranslator:
    """Records every provider call so fan-out dedup is provable."""

    def __init__(self, fail_for: str | None = None) -> None:
        self.calls: list[tuple[str, str, tuple[str, ...]]] = []
        self.fail_for = fail_for

    async def translate(self, text: str, source_lang: str, target_lang: str,
                        context: tuple[str, ...] = (), *,
                        segment_id: str | None = None,
                        speaker_id: str | None = None):
        self.calls.append((source_lang, target_lang, tuple(context)))
        if self.fail_for == target_lang:
            raise LookupError(f"pair {source_lang}->{target_lang} is not supported")
        return ProviderTranslation(text=f"[{target_lang}] {text}", provider="fake",
                                   model="fake-mt", latency_ms=42.0)


class FakeTts:
    def __init__(self, chunks: int = 3, fail: bool = False) -> None:
        self.chunks = chunks
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    async def synthesize_stream(self, text: str, lang: str, voice: str | None = None):
        self.calls.append((lang, text))
        if self.fail:
            raise RuntimeError("tts provider down")

        async def stream():
            for i in range(self.chunks):
                yield AudioChunk(data=b"\x00" * (320 * (i + 1)), sample_rate=24000,
                                 encoding="pcm_s16le", format="wav", provider="fake",
                                 model="fake-tts", duration_ms=400.0, is_dev=True)
        return stream(), _decision("fake-tts", "tts")


def _translation_segment(corr: str = "utt-1", segment_id: str = "seg-1",
                         target: str = "en") -> TranslationSegment:
    return TranslationSegment(correlation_id=corr, meeting_id=MEETING,
                              speaker_id=SPEAKER, recipient_id=LISTENER_EN_1,
                              source_segment_id=segment_id, source_language="hi",
                              target_language=target, translated_text="Hello, how are you?",
                              source_start_time_ms=10_000, source_end_time_ms=11_200)


def _transcript_segment(text: str = HINDI, source_lang: str = "hi",
                        is_final: bool = True, seq: int = 1) -> TranscriptSegment:
    return TranscriptSegment(correlation_id="utt-1", meeting_id=MEETING,
                             speaker_id=SPEAKER, segment_id=str(uuid.uuid4()),
                             sequence_number=seq, source_language=source_lang,
                             recognized_text=text, start_time_ms=10_000,
                             end_time_ms=11_200, is_final=is_final)


async def _no_delivery(chunk, audio, recipients):
    return None


# --------------------------------------------------------------------------- #
# Agent 1 — listening
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_agent1_capture_partial_final_share_one_stable_segment_id():
    bus = AgentBus(clock=FakeClock())
    stt = FakeStt()
    agent = ListeningAgent(bus, stt, meeting_id=MEETING)
    segment_id = str(uuid.uuid4())

    await agent.on_audio_captured(correlation_id="utt-1", speaker_id=SPEAKER,
                                  segment_id=segment_id, start_ms=10_000,
                                  sequence_number=1, audio_bytes=32_000)
    partial = await agent.transcribe_partial(correlation_id="utt-1", speaker_id=SPEAKER,
                                             segment_id=segment_id, sequence_number=1,
                                             audio=b"\x01" * 16_000)
    assert partial is not None and partial.is_final is False
    assert partial.segment_id == segment_id

    final = await agent.finalize(correlation_id="utt-1", speaker_id=SPEAKER,
                                 segment_id=segment_id, sequence_number=1,
                                 audio=b"\x01" * 32_000, start_ms=10_000, end_ms=11_200)
    assert isinstance(final, TranscriptSegment)
    assert final.is_final is True
    assert final.recognized_text == HINDI
    assert final.source_language == "hi"
    assert final.confidence == pytest.approx(0.92)
    assert final.end_time_ms == 11_200

    assert [e.type for e in bus.trace] == [
        Stage.AUDIO_CAPTURED, Stage.TRANSCRIPT_PARTIAL, Stage.TRANSCRIPT_FINAL,
    ]
    assert {e.segment_id for e in bus.trace} == {segment_id}
    assert {e.correlation_id for e in bus.trace} == {"utt-1"}
    # revision advances across partials and the single finalize
    assert bus.trace[1].payload["transcript_revision"] == 1
    assert bus.trace[2].payload["transcript_revision"] == 2
    # audio frames are summarized by size only — never carried on the bus
    assert bus.trace[0].payload["audio_bytes"] == 32_000

    # finalizing the same segment twice must not produce a second final event
    again = await agent.finalize(correlation_id="utt-1", speaker_id=SPEAKER,
                                 segment_id=segment_id, sequence_number=1,
                                 audio=b"\x01" * 32_000, start_ms=10_000, end_ms=11_200)
    assert again is None
    assert [e.type for e in bus.trace].count(Stage.TRANSCRIPT_FINAL) == 1


@pytest.mark.asyncio
async def test_agent1_subthreshold_audio_produces_no_transcript():
    bus = AgentBus()
    agent = ListeningAgent(bus, FakeStt(), meeting_id=MEETING)
    assert await agent.finalize(correlation_id="u", speaker_id=SPEAKER,
                                segment_id="s", sequence_number=1,
                                audio=b"\x00" * 100, start_ms=0, end_ms=6) is None
    assert bus.trace == []
    assert agent.stt.calls == []          # provider never invoked for noise


@pytest.mark.asyncio
async def test_agent1_reports_empty_speech_and_provider_timeout():
    quiet = ListeningAgent(bus1 := AgentBus(), FakeStt(text="   "), meeting_id=MEETING)
    assert await quiet.finalize(correlation_id="u", speaker_id=SPEAKER,
                                segment_id="s1", sequence_number=1,
                                audio=b"\x00" * 16_000, start_ms=0, end_ms=500) is None
    assert bus1.trace[-1].type is Stage.STAGE_FAILED
    assert bus1.trace[-1].payload["reason"] == "empty_speech"
    assert bus1.trace[-1].payload["stage"] == "stt"

    broken = ListeningAgent(bus2 := AgentBus(), RaisingStt(), meeting_id=MEETING)
    assert await broken.finalize(correlation_id="u", speaker_id=SPEAKER,
                                 segment_id="s2", sequence_number=1,
                                 audio=b"\x00" * 16_000, start_ms=0, end_ms=500) is None
    failed = bus2.trace[-1]
    assert failed.type is Stage.STAGE_FAILED
    assert failed.payload["stage"] == "stt"
    assert failed.payload["recoverable"] is True
    assert failed.payload["error_code"] == "TimeoutError"


# --------------------------------------------------------------------------- #
# Agent 2 — translation and per-recipient fan-out
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_agent2_calls_the_provider_once_per_distinct_language_per_recipient():
    translator = FakeTranslator()
    bus = AgentBus()
    agent = TranslationAgent(bus, translator, meeting_id=MEETING)

    out = await agent.fan_out(_transcript_segment(),
                              recipients_by_lang={"en": [LISTENER_EN_1, LISTENER_EN_2],
                                                  "ur": [LISTENER_UR]})
    assert len(translator.calls) == 2                       # 3 recipients, 2 languages
    assert {(src, tgt) for src, tgt, _ in translator.calls} == {("hi", "en"), ("hi", "ur")}
    assert len(out) == 3                                    # one per recipient
    assert sum(1 for t in out if t.target_language == "en") == 2
    assert {e.type for e in bus.trace} == {Stage.TRANSLATION_READY}
    assert len(bus.trace) == 3
    # the two English recipients share one provider result, not two calls
    en_texts = {e.payload["translated_text"] for e in bus.trace
                if e.payload["target_language"] == "en"}
    assert en_texts == {f"[en] {HINDI}"}
    assert {e.recipient_id for e in bus.trace} == {LISTENER_EN_1, LISTENER_EN_2, LISTENER_UR}
    # canonical source text is preserved alongside the translation
    assert bus.trace[0].payload["source_text"] == HINDI


@pytest.mark.asyncio
async def test_agent2_never_translates_unstable_partials():
    translator = FakeTranslator()
    bus = AgentBus()
    agent = TranslationAgent(bus, translator, meeting_id=MEETING)
    assert await agent.fan_out(_transcript_segment(is_final=False),
                               recipients_by_lang={"en": [LISTENER_EN_1]}) == []
    assert translator.calls == []
    assert bus.trace == []


@pytest.mark.asyncio
async def test_agent2_skips_identity_pairs_and_reports_unsupported_languages():
    translator = FakeTranslator(fail_for="mr")
    bus = AgentBus()
    agent = TranslationAgent(bus, translator, meeting_id=MEETING)
    out = await agent.fan_out(_transcript_segment(),
                              recipients_by_lang={"hi": [LISTENER_EN_1],       # == source
                                                  "mr": [LISTENER_UR]})
    assert out == []
    assert [(s, t) for s, t, _ in translator.calls] == [("hi", "mr")]   # identity skipped
    assert bus.trace[-1].type is Stage.STAGE_FAILED
    assert bus.trace[-1].payload["stage"] == "translation"
    assert bus.trace[-1].payload["target_language"] == "mr"
    assert bus.trace[-1].payload["recoverable"] is True
    # the guide forbids inventing missing words — no text is claimed
    assert "translated_text" not in bus.trace[-1].payload


@pytest.mark.asyncio
async def test_agent2_keeps_per_speaker_context_bounded():
    bus = AgentBus()
    agent = TranslationAgent(bus, (spy := FakeTranslator()), meeting_id=MEETING,
                             context_limit=2)
    for i in range(5):
        await agent.fan_out(_transcript_segment(text=f"line {i}", seq=i + 1),
                            recipients_by_lang={"en": [LISTENER_EN_1]})
    contexts = [c for _, _, c in spy.calls]
    assert len(contexts) == 5
    assert all(len(c) <= 2 for c in contexts)
    assert contexts[0] == ()
    assert contexts[-1] == ("line 2", "line 3")
    # a different speaker never sees this speaker's context
    other = _transcript_segment(text="duos", seq=1)
    other.speaker_id = str(uuid.uuid4())
    await agent.fan_out(other, recipients_by_lang={"en": [LISTENER_EN_1]})
    assert spy.calls[-1][2] == ()


# --------------------------------------------------------------------------- #
# Agent 3 — voice
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_agent3_declares_chunk_metadata_and_keeps_audio_off_the_bus():
    bus = AgentBus()
    sent: list[tuple[int, list[str]]] = []

    async def deliver(chunk, audio: bytes, recipients):
        sent.append((len(audio), recipients))

    tts = FakeTts(chunks=3)
    agent = VoiceAgent(bus, tts, meeting_id=MEETING)
    count = await agent.synthesize(_translation_segment(),
                                   recipients=[LISTENER_EN_1, LISTENER_EN_2],
                                   deliver=deliver)
    assert count == 3
    assert tts.calls == [("en", "Hello, how are you?")]

    ready = [e for e in bus.trace if e.type is Stage.TTS_CHUNK_READY]
    assert [e.payload["chunk_index"] for e in ready] == [0, 1, 2]
    assert ready[0].payload["codec"] == "wav"
    assert ready[0].payload["sample_rate"] == 24000
    assert ready[0].payload["channels"] == 1
    assert ready[0].payload["duration_ms"] == 400.0
    assert ready[0].payload["recipient_ids"] == [LISTENER_EN_1, LISTENER_EN_2]
    assert [e.payload["payload_bytes"] for e in ready] == [320, 640, 960]

    assert bus.trace[-1].type is Stage.AUDIO_DELIVERED
    assert bus.trace[-1].payload["chunks_delivered"] == 3
    assert bus.trace[-1].payload["total_bytes"] == 1920

    assert sent == [(320, [LISTENER_EN_1, LISTENER_EN_2]),
                    (640, [LISTENER_EN_1, LISTENER_EN_2]),
                    (960, [LISTENER_EN_1, LISTENER_EN_2])]
    # no event on the bus carries raw audio
    for event in bus.trace:
        assert not any(isinstance(v, bytes) for v in event.payload.values())
        assert "audio_base64" not in event.payload


@pytest.mark.asyncio
async def test_agent3_reports_failure_and_keeps_the_original_audio_path():
    bus = AgentBus()
    agent = VoiceAgent(bus, FakeTts(fail=True), meeting_id=MEETING)
    assert await agent.synthesize(_translation_segment(),
                                  recipients=[LISTENER_EN_1], deliver=_no_delivery) == 0
    failed = bus.trace[-1]
    assert failed.type is Stage.STAGE_FAILED
    assert failed.payload["stage"] == "tts"
    assert failed.payload["error_code"] == "RuntimeError"
    assert failed.payload["recoverable"] is True
    # non-negotiable: the original conversation stays available
    assert failed.payload["original_audio_available"] is True


@pytest.mark.asyncio
async def test_agent3_uses_one_channel_per_recipient_group_and_tags_recipients():
    bus = AgentBus()
    agent = VoiceAgent(bus, FakeTts(chunks=1), meeting_id=MEETING)
    await agent.synthesize(_translation_segment(target="ur"),
                           recipients=[LISTENER_UR], deliver=_no_delivery)
    chunk = [e for e in bus.trace if e.type is Stage.TTS_CHUNK_READY][0]
    assert chunk.payload["target_language"] == "ur"
    assert chunk.payload["recipient_ids"] == [LISTENER_UR]


# --------------------------------------------------------------------------- #
# Agent 4 — supervisor, over the whole trace
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_agents_1_to_4_produce_one_ordered_trace_per_correlation_id():
    clock = FakeClock()
    bus = AgentBus(clock=clock)
    supervisor = Supervisor()
    supervisor.attach(bus)

    listening = ListeningAgent(bus, FakeStt(), meeting_id=MEETING)
    translator = TranslationAgent(bus, FakeTranslator(), meeting_id=MEETING)
    voice = VoiceAgent(bus, FakeTts(chunks=2), meeting_id=MEETING)
    segment_id = str(uuid.uuid4())

    async def deliver(chunk, audio, recipients):
        clock.advance(10)

    await listening.on_audio_captured(correlation_id="utt-9", speaker_id=SPEAKER,
                                      segment_id=segment_id, start_ms=0,
                                      sequence_number=1, audio_bytes=32_000)
    clock.advance(120)
    final = await listening.finalize(correlation_id="utt-9", speaker_id=SPEAKER,
                                     segment_id=segment_id, sequence_number=1,
                                     audio=b"\x01" * 32_000, start_ms=0, end_ms=1_200)
    clock.advance(300)
    translations = await translator.fan_out(final,
                                            recipients_by_lang={"en": [LISTENER_EN_1]})
    clock.advance(80)
    await voice.synthesize(translations[0], recipients=[LISTENER_EN_1], deliver=deliver)

    assert [e.type for e in bus.trace] == [
        Stage.AUDIO_CAPTURED, Stage.TRANSCRIPT_FINAL, Stage.TRANSLATION_READY,
        Stage.TTS_CHUNK_READY, Stage.TTS_CHUNK_READY, Stage.AUDIO_DELIVERED,
    ]
    assert {e.correlation_id for e in bus.trace} == {"utt-9"}
    assert {e.meeting_id for e in bus.trace} == {MEETING}
    assert {e.version for e in bus.trace} == {1}
    assert all(e.event_id for e in bus.trace)
    assert [e.timestamp_ms for e in bus.trace] == sorted(e.timestamp_ms for e in bus.trace)

    report = supervisor.segment_report("utt-9")
    assert report["source_language"] == "hi"
    assert report["target_language"] == "en"
    assert report["stt_ms"] == 120
    assert report["translation_ms"] == 300
    assert report["tts_first_audio_ms"] == 80
    assert report["speech_to_first_translated_audio_ms"] == 500
    assert report["chunks_expected"] == 2
    assert report["chunks_delivered"] == 2
    assert report["missing_chunks"] == 0
    assert report["stages"] == [
        "audio_captured", "transcript_final", "translation_ready",
        "tts_chunk_ready", "audio_delivered",
    ]


@pytest.mark.asyncio
async def test_agent4_separates_duplicate_late_reordered_and_missing_chunks():
    bus = AgentBus()
    supervisor = Supervisor()
    supervisor.attach(bus)
    agent = VoiceAgent(bus, FakeTts(chunks=1), meeting_id=MEETING)
    delivered: list[int] = []

    async def deliver(chunk, audio, recipients):
        delivered.append(chunk.chunk_index)

    translation = _translation_segment(corr="utt-d", segment_id="seg-d")
    # 2 first, then a replay of 2, then 0, then 1 — the transport sees each index once
    for index in (2, 2, 0, 1):
        await agent.publish_chunk(translation, index=index, audio=b"x" * 100,
                                  duration_ms=400, recipients=[LISTENER_EN_1],
                                  deliver=deliver)

    assert delivered == [2, 0, 1]                       # duplicate never reaches transport
    assert supervisor.metrics["duplicate_chunks"] == 1
    assert supervisor.metrics["late_chunks"] == 2       # 0 and 1 both trailed index 2
    assert supervisor.metrics["reordered_chunks"] == 1  # only the 2 -> 0 step is a reorder
    events = [e for e in bus.trace if e.type is Stage.TTS_CHUNK_READY]
    assert [e.payload["chunk_index"] for e in events] == [2, 2, 0, 1]
    assert events[0].payload.get("duplicate") is None    # first arrival is real
    assert events[1].payload["duplicate"] is True         # observed, but not re-delivered

    # a segment that stops mid-stream reports the hole instead of hiding it
    gap = Supervisor()
    gap_bus = AgentBus()
    gap.attach(gap_bus)
    gap_agent = VoiceAgent(gap_bus, FakeTts(chunks=1), meeting_id=MEETING)
    await gap_agent.publish_chunk(_translation_segment(corr="utt-g", segment_id="seg-g"),
                                  index=0, audio=b"x", duration_ms=400,
                                  recipients=[LISTENER_EN_1], deliver=_no_delivery)
    await gap_agent.publish_chunk(_translation_segment(corr="utt-g", segment_id="seg-g"),
                                  index=3, audio=b"x", duration_ms=400,
                                  recipients=[LISTENER_EN_1], deliver=_no_delivery)
    await gap_agent.finish_delivery(_translation_segment(corr="utt-g", segment_id="seg-g"),
                                    recipients=[LISTENER_EN_1])
    assert gap.segment_report("utt-g")["missing_chunks"] == 2


@pytest.mark.asyncio
async def test_agent4_interrupt_cancels_only_the_interrupted_speaker():
    bus = AgentBus()
    supervisor = Supervisor()
    supervisor.attach(bus)
    supervisor.note_active_segment(SPEAKER, correlation_id="utt-a", sequence_number=1,
                                  target_languages=["en"])
    supervisor.note_active_segment("other-speaker", correlation_id="utt-b",
                                   sequence_number=1, target_languages=["en"])

    await supervisor.interrupt(SPEAKER, reason="barge_in")
    assert supervisor.is_cancelled("utt-a") is True
    assert supervisor.is_cancelled("utt-b") is False
    assert bus.trace[-1].type is Stage.INTERRUPT
    assert bus.trace[-1].speaker_id == SPEAKER
    assert bus.trace[-1].payload["reason"] == "barge_in"
    assert bus.trace[-1].payload["correlation_id"] == "utt-a"

    assert await supervisor.guard("utt-a") is False
    assert await supervisor.guard("utt-b") is True
    assert supervisor.metrics["cancelled_drops"] == 1


@pytest.mark.asyncio
async def test_agent4_target_language_change_cancels_stale_output():
    bus = AgentBus()
    supervisor = Supervisor()
    supervisor.attach(bus)
    supervisor.note_active_segment(SPEAKER, correlation_id="utt-x", sequence_number=1,
                                   target_languages=["en"])
    await supervisor.recipient_changed(LISTENER_EN_1, previous_language="en",
                                       new_language="ur")
    assert supervisor.is_stale_for(LISTENER_EN_1, "en") is True
    assert supervisor.is_stale_for(LISTENER_EN_2, "en") is False
    # the segment itself stays live — other listeners still get it
    assert supervisor.is_cancelled("utt-x") is False
    assert supervisor.live_recipients([LISTENER_EN_1, LISTENER_EN_2], "en") == [LISTENER_EN_2]
    assert bus.trace[-1].type is Stage.INTERRUPT
    assert bus.trace[-1].payload["reason"] == "language_changed"
    assert bus.trace[-1].payload["scope"] == "recipient"


@pytest.mark.asyncio
async def test_agent4_switching_back_to_a_language_un_stales_it():
    """Staleness is a fact about the *past* turn, not a permanent subscription.

    Marking (listener, "en") stale on en→ur is right; leaving it stale when the
    same listener picks English again means they never hear English for the rest
    of the meeting, because nothing else ever clears the set.
    """
    bus = AgentBus()
    supervisor = Supervisor()
    supervisor.attach(bus)
    await supervisor.recipient_changed(LISTENER_EN_1, previous_language="en",
                                       new_language="ur")
    assert supervisor.is_stale_for(LISTENER_EN_1, "en") is True

    await supervisor.recipient_changed(LISTENER_EN_1, previous_language="ur",
                                       new_language="en")

    assert supervisor.is_stale_for(LISTENER_EN_1, "en") is False
    assert supervisor.is_stale_for(LISTENER_EN_1, "ur") is True
    # and somebody else's choice is still not this listener's business
    assert supervisor.is_stale_for(LISTENER_EN_2, "en") is False


@pytest.mark.asyncio
async def test_agent4_bounds_the_queue_and_counts_drops_instead_of_stalling_audio():
    bus = AgentBus(maxsize=2)
    for i in range(10):
        await bus.publish(RealtimeEvent(type=Stage.TTS_CHUNK_READY,
                                        correlation_id=f"c{i}", meeting_id=MEETING,
                                        segment_id="s", payload={"chunk_index": i}))
    assert bus.dropped == 8                 # overflow is counted, never blocked on
    assert bus.health()["queue_depth"] == 2
    assert len(bus.trace) == 10             # in-process trace is not the drop point


@pytest.mark.asyncio
async def test_agent4_emits_session_closed_once():
    bus = AgentBus()
    supervisor = Supervisor()
    supervisor.attach(bus)
    await supervisor.close()
    await supervisor.close()
    assert [e.type for e in bus.trace].count(Stage.SESSION_CLOSED) == 1
    assert supervisor.health()["closed"] is True

@pytest.mark.asyncio
async def test_stage_bookkeeping_stays_bounded_over_a_long_meeting():
    """A room open for hours must not accumulate one entry per 40 ms frame.

    Dedup and ordering state exist to catch a replay, which is a recent-history
    question. Unbounded history is how a working meeting leaks.
    """
    bus = AgentBus()
    supervisor = Supervisor(meeting_id=MEETING, record_limit=32)
    supervisor.attach(bus)
    voice = VoiceAgent(bus, FakeTts(chunks=2), meeting_id=MEETING, seen_limit=64)

    async def deliver(chunk, audio, recipients):
        return None

    for i in range(200):
        await voice.synthesize(_translation_segment(corr=f"utt-{i}", segment_id=f"seg-{i}"),
                               recipients=[LISTENER_EN_1], deliver=deliver)

    assert len(voice._seen) <= 64                  # oldest chunk keys evicted
    assert voice._deliveries == {}                 # closed segments hold nothing
    assert len(supervisor._records) <= 32          # and neither does Agent 4
    assert supervisor.metrics["duplicate_chunks"] == 0

@pytest.mark.asyncio
async def test_an_interrupted_run_can_retry_without_being_judged_a_duplicate():
    """Chunk dedup protects a live segment; an aborted one must be replayable."""
    voice = VoiceAgent(AgentBus(), FakeTts(chunks=2), meeting_id=MEETING)
    delivered: list[int] = []

    async def deliver(chunk, audio, recipients):
        delivered.append(chunk.chunk_index)

    seg = _translation_segment(corr="utt-i", segment_id="seg-i")
    await voice.synthesize(seg, recipients=[LISTENER_EN_1], deliver=deliver)
    await voice.synthesize(seg, recipients=[LISTENER_EN_1], deliver=deliver)
    assert delivered == [0, 1]                 # the replay is suppressed

    voice.forget_segment("utt-i", "seg-i")     # the listener interrupted it
    await voice.synthesize(seg, recipients=[LISTENER_EN_1], deliver=deliver)
    assert delivered == [0, 1, 0, 1]           # so the retry is a fresh run
