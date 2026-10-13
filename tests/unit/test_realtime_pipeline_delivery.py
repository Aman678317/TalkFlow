"""Tree A realtime pipeline — stage bodies driven with fake providers.

Why this file exists: CI runs ``tests/unit``, ``tests/integration`` and
``tests/realtime``, but the golden call starts ``globaltalk.main:app`` (Tree B).
Nothing in CI exercised the pipeline that is actually deployed
(``services/api/app/realtime/pipeline.py``). Its two stage bodies —
``_finalize_utterance`` and ``_translate_and_synthesize`` — are where translated
audio is either delivered or silently lost, so they are now tested directly.

These tests use the real ``SessionManager`` routing and the real wire protocol;
only the AI providers and the DB session are faked. That keeps listener
selection, event sequencing and the binary frame layout under test rather than
re-implemented.
"""
from __future__ import annotations

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
    def __init__(self, chunk: TranscriptChunk | None = None,
                 raise_stt: Exception | None = None,
                 tts_chunks: int = 2, raise_tts: Exception | None = None,
                 fail_tts_for: str | None = None) -> None:
        self.chunk = chunk or TranscriptChunk(
            text="नमस्ते", language="auto", is_final=True, confidence=0.9,
            model="fake-stt", provider="fake")
        self.raise_stt = raise_stt
        self.raise_tts = raise_tts
        self.fail_tts_for = fail_tts_for
        self.tts_chunks = tts_chunks
        self.transcribe_calls: list[tuple[int, str | None]] = []
        self.synthesize_calls: list[tuple[str, str]] = []

    async def transcribe(self, audio: bytes, sample_rate: int,
                         lang_hint: str | None = None):
        self.transcribe_calls.append((len(audio), lang_hint))
        if self.raise_stt:
            raise self.raise_stt
        return self.chunk, _decision("fake-stt", "stt")

    async def detect_language(self, text: str) -> DetectionResult:
        return DetectionResult(language="hi", confidence=0.88, provider="fake-detect")

    async def synthesize_stream(self, text: str, lang: str, voice: str | None = None):
        self.synthesize_calls.append((text, lang))
        if self.raise_tts or self.fail_tts_for == lang:
            raise self.raise_tts or RuntimeError(f"tts down for {lang}")
        n = self.tts_chunks

        async def stream():
            for i in range(n):
                yield AudioChunk(data=b"\x54\x48" * (40 * (i + 1)), sample_rate=24000,
                                 encoding="pcm_s16le", format="wav", provider="fake-tts",
                                 model="fake-tts-m", duration_ms=250.0)
        return stream(), _decision("fake-tts", "tts")

    def is_dev_mode(self, task) -> bool:
        return True


def _participant(*, hear: str, mode: str = "translated",
                 captions: bool = True) -> RtParticipant:
    return RtParticipant(participant_id=uuid.uuid4(), user_id=None,
                         display_name=f"listener-{hear}", speak_lang="auto",
                         hear_lang=hear, audio_mode=mode, captions_enabled=captions,
                         ws=FakeWs(), connected=True)


@pytest.fixture
def session():
    return RtSession(session_id="sess-1", meeting_id=uuid.uuid4(),
                     org_id=uuid.uuid4(), room_name="room", mode="ws")


@pytest.fixture
def no_db(monkeypatch):
    """Stage bodies must not need a database to be tested."""
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


PRIOR_TURN = "पहली बात"   # "the first thing"


def _utt(speaker: RtParticipant) -> P.UtteranceState:
    """An in-flight utterance as the speaker loop would have built it."""
    return P.UtteranceState(participant_id=speaker.participant_id,
                            capture_started=time.perf_counter(), started_at_ms=0, seq=1,
                            in_speech=False)


def _join(session: RtSession, *participants: RtParticipant) -> None:
    for p in participants:
        manager.add_participant(session, p)


def _events(ws: FakeWs, event_type: str) -> list[dict]:
    return [e for e in ws.events if e.get("type") == event_type]


# --------------------------------------------------------------------------- #
# Agent-1 equivalent: STT stage body
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_below_threshold_audio_never_reaches_the_stt_provider(session, speaker,
                                                                    monkeypatch):
    ai = FakeAI()
    monkeypatch.setattr(P, "ai", ai)
    pipe = P.MeetingPipeline(session)
    committed = []
    monkeypatch.setattr(pipe, "_commit_segment", lambda *a, **kw: committed.append(kw))

    u = _utt(speaker)
    await pipe._finalize_utterance(speaker, u, audio_bytes=b"\x00" * 800,
                                   utterance_id=u.utterance_id, seq=1)

    assert ai.transcribe_calls == []
    assert committed == []


@pytest.mark.asyncio
async def test_stt_failure_emits_a_recoverable_error_and_keeps_the_meeting(
        session, speaker, monkeypatch):
    ai = FakeAI(raise_stt=RuntimeError("model missing"))
    monkeypatch.setattr(P, "ai", ai)
    _join(session, speaker)
    pipe = P.MeetingPipeline(session)
    u = _utt(speaker)

    await pipe._finalize_utterance(speaker, u, audio_bytes=b"\x00" * 32_000,
                                   utterance_id=u.utterance_id, seq=1)

    errors = _events(speaker.ws, "error")
    assert errors and errors[0]["code"] == "stt_unavailable"
    assert errors[0]["recoverable"] is True
    assert _events(speaker.ws, "transcript.final") == []


@pytest.mark.asyncio
async def test_empty_transcript_does_not_fan_out(session, speaker, monkeypatch):
    ai = FakeAI(chunk=TranscriptChunk(text="   ", language="hi", is_final=True))
    monkeypatch.setattr(P, "ai", ai)
    _join(session, speaker)
    pipe = P.MeetingPipeline(session)
    committed = []
    monkeypatch.setattr(pipe, "_commit_segment", lambda *a, **kw: committed.append(kw))

    u = _utt(speaker)
    await pipe._finalize_utterance(speaker, u, audio_bytes=b"\x00" * 32_000,
                                   utterance_id=u.utterance_id, seq=1)

    assert committed == []
    ended = _events(speaker.ws, "speech.ended")
    assert ended and ended[-1]["empty"] is True


@pytest.mark.asyncio
async def test_auto_language_is_resolved_before_the_segment_is_committed(
        session, speaker, monkeypatch):
    ai = FakeAI()
    monkeypatch.setattr(P, "ai", ai)
    pipe = P.MeetingPipeline(session)
    captured: dict = {}

    async def record(_p, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(pipe, "_commit_segment", record)
    u = _utt(speaker)
    u.locked_language = None

    await pipe._finalize_utterance(speaker, u, audio_bytes=b"\x00" * 32_000,
                                   utterance_id=u.utterance_id, seq=3)
    # provider said "auto", so detection supplied the canonical source language
    assert captured["source_lang"] == "hi"
    assert captured["seq_num"] == 3
    assert captured["utterance_id"] == u.utterance_id


# --------------------------------------------------------------------------- #
# Agent-2 / Agent-3 equivalent: fan-out, synthesis, delivery
# --------------------------------------------------------------------------- #

def _translation_result(text: str, src: str, tgt: str) -> TranslationResult:
    return TranslationResult(text=text, source_lang=src, target_lang=tgt,
                             model="fake-mt", provider="fake-mt", latency_ms=12.0,
                             quality_flags=["tm_hit"])


@pytest.mark.asyncio
async def test_each_distinct_target_language_is_translated_exactly_once(
        session, speaker, no_db, monkeypatch):
    en_1, en_2, ur = _participant(hear="en"), _participant(hear="en"), _participant(hear="ur")
    _join(session, speaker, en_1, en_2, ur)

    calls: list[tuple[str, str]] = []
    ai = FakeAI()
    monkeypatch.setattr(P, "ai", ai)

    async def fake_translate(db, text, src, tgt, ctx):
        calls.append((src, tgt))
        return SimpleNamespace(result=_translation_result(f"[{tgt}] {text}", src, tgt))

    monkeypatch.setattr(P, "translate_text", fake_translate)
    pipe = P.MeetingPipeline(session)
    segment_id = uuid.uuid4()

    await pipe._translate_and_synthesize(
        segment_id=segment_id, seq=1, speaker=speaker, text="नमस्ते",
        source_lang="hi", target_lang="en", stt_ms=10.0, capture_ms=5.0)
    await pipe._translate_and_synthesize(
        segment_id=segment_id, seq=1, speaker=speaker, text="नमस्ते",
        source_lang="hi", target_lang="ur", stt_ms=10.0, capture_ms=5.0)

    assert calls == [("hi", "en"), ("hi", "ur")]          # once per language, not per listener
    assert len(_events(en_1.ws, "tts.chunk")) == 2        # two chunks each
    assert len(_events(en_2.ws, "tts.chunk")) == 2
    assert len(_events(ur.ws, "tts.chunk")) == 2
    # a listener never receives another language's audio
    assert all(e["target_language"] == "en" for e in _events(en_1.ws, "tts.chunk"))
    assert all(e["target_language"] == "ur" for e in _events(ur.ws, "tts.chunk"))


@pytest.mark.asyncio
async def test_json_chunk_and_binary_frame_agree_on_one_segment_identity(
        session, speaker, no_db, monkeypatch):
    """The invariant the browser's dedup depends on, asserted server-side.

    Both transports must normalize to the same 16-char key, or the client plays
    the same chunk twice (or thinks two chunks are one).
    """
    en = _participant(hear="en")
    _join(session, speaker, en)
    ai = FakeAI(tts_chunks=3)
    monkeypatch.setattr(P, "ai", ai)

    async def fake_translate(db, text, src, tgt, ctx):
        return SimpleNamespace(result=_translation_result("Hello", src, tgt))

    monkeypatch.setattr(P, "translate_text", fake_translate)
    pipe = P.MeetingPipeline(session)
    segment_id = uuid.uuid4()

    await pipe._translate_and_synthesize(
        segment_id=segment_id, seq=7, speaker=speaker, text="नमस्ते",
        source_lang="hi", target_lang="en", stt_ms=10.0, capture_ms=5.0)

    chunks = _events(en.ws, "tts.chunk")
    assert [c["chunk_index"] for c in chunks] == [0, 1, 2]
    assert len(en.ws.frames) == 3

    def norm(raw: str) -> str:
        """Mirror of the browser's normId(): cut to 16 chars, *then* strip padding."""
        return raw.replace("-", "")[:16].rstrip("\x00").rstrip("0")

    for event, frame in zip(chunks, en.ws.frames):
        assert frame[0] == 0x54                      # 'T' — translated audio
        binary_id = frame[1:17].decode("utf-8", "replace")
        assert norm(binary_id) == norm(event["segment_id"])
        lang_len = frame[17]
        assert frame[18:18 + lang_len].decode() == "en"
        assert frame[18 + lang_len:] == __import__("base64").b64decode(event["audio_base64"])
    completed = _events(en.ws, "tts.completed")
    assert completed[-1]["chunks"] == 3


@pytest.mark.asyncio
async def test_translation_failure_for_one_language_does_not_stop_another(
        session, speaker, no_db, monkeypatch):
    en, ur = _participant(hear="en"), _participant(hear="ur")
    _join(session, speaker, en, ur)
    monkeypatch.setattr(P, "ai", FakeAI())

    async def failing_for_ur(db, text, src, tgt, ctx):
        if tgt == "ur":
            raise RuntimeError("pair unavailable")
        return SimpleNamespace(result=_translation_result("Hello", src, tgt))

    monkeypatch.setattr(P, "translate_text", failing_for_ur)
    pipe = P.MeetingPipeline(session)

    for lang in ("ur", "en"):
        await pipe._translate_and_synthesize(
            segment_id=uuid.uuid4(), seq=1, speaker=speaker, text="नमस्ते",
            source_lang="hi", target_lang=lang, stt_ms=1.0, capture_ms=1.0)

    failed = _events(ur.ws, "translation.failed") + _events(en.ws, "translation.failed")
    assert failed and failed[0]["target_lang"] == "ur"
    assert failed[0]["recoverable"] is True
    # English listeners are unaffected
    assert _events(en.ws, "tts.chunk")
    assert _events(ur.ws, "tts.chunk") == []


@pytest.mark.asyncio
async def test_tts_failure_leaves_translated_captions_intact(session, speaker, no_db,
                                                             monkeypatch):
    en = _participant(hear="en")
    _join(session, speaker, en)
    monkeypatch.setattr(P, "ai", FakeAI(raise_tts=RuntimeError("voice missing")))

    async def fake_translate(db, text, src, tgt, ctx):
        return SimpleNamespace(result=_translation_result("Hello", src, tgt))

    monkeypatch.setattr(P, "translate_text", fake_translate)
    pipe = P.MeetingPipeline(session)

    await pipe._translate_and_synthesize(
        segment_id=uuid.uuid4(), seq=2, speaker=speaker, text="नमस्ते",
        source_lang="hi", target_lang="en", stt_ms=1.0, capture_ms=1.0)

    assert _events(en.ws, "translation.final")            # caption survived
    assert _events(en.ws, "tts.chunk") == []
    assert en.ws.frames == []
    errors = _events(en.ws, "error")
    assert errors and errors[0]["code"] == "tts_unavailable"
    assert errors[0]["recoverable"] is True


@pytest.mark.asyncio
async def test_stale_segment_is_dropped_before_it_can_talk_over_current_speech(
        session, speaker, no_db, monkeypatch):
    en = _participant(hear="en")
    _join(session, speaker, en)
    monkeypatch.setattr(P, "ai", FakeAI())
    called = []

    async def fake_translate(db, text, src, tgt, ctx):
        called.append(tgt)
        return SimpleNamespace(result=_translation_result("Hello", src, tgt))

    monkeypatch.setattr(P, "translate_text", fake_translate)
    pipe = P.MeetingPipeline(session)
    pipe._latest_final_seq[speaker.participant_id] = 9   # speaker has moved on

    await pipe._translate_and_synthesize(
        segment_id=uuid.uuid4(), seq=3, speaker=speaker, text="नमस्ते",
        source_lang="hi", target_lang="en", stt_ms=1.0, capture_ms=1.0)

    assert called == []
    assert _events(en.ws, "tts.chunk") == []
    # The drop is silent on the wire by design (PDD §10): the counter is
    # STALE_AUDIO_DROPPED{reason="pre_translation"}, not an event.
    assert en.ws.events == []
    assert en.ws.frames == []


@pytest.mark.asyncio
async def test_original_audio_relay_only_reaches_original_and_mixed_listeners(
        session, speaker, monkeypatch):
    original = _participant(hear="hi", mode="original")
    mixed = _participant(hear="hi", mode="mixed")
    translated = _participant(hear="en", mode="translated")
    _join(session, speaker, original, mixed, translated)

    await manager.relay_audio(session, speaker.participant_id, b"\x01\x02" * 100)

    assert len(original.ws.frames) == 1
    assert len(mixed.ws.frames) == 1
    assert translated.ws.frames == []
    assert original.ws.frames[0][0] == 0x4F               # 'O' — original audio


@pytest.mark.asyncio
async def test_one_languages_tts_failure_does_not_condemn_another(
        session, speaker, no_db, monkeypatch):
    """Two languages of one segment must not share failure or dedup state.

    One source segment fans out to several target languages under one
    correlation id. If the voice agent keys its dedup and failure bookkeeping on
    the utterance alone, the second language's chunk 0 looks like a duplicate of
    the first's and is never delivered, or a French outage silences Hindi
    listeners too.
    """
    en, ur = _participant(hear="en"), _participant(hear="ur")
    _join(session, speaker, en, ur)
    monkeypatch.setattr(P, "ai", FakeAI(fail_tts_for="ur"))

    async def fake_translate(db, text, src, tgt, ctx):
        return SimpleNamespace(result=_translation_result(f"[{tgt}] {text}", src, tgt))

    monkeypatch.setattr(P, "translate_text", fake_translate)
    pipe = P.MeetingPipeline(session)
    segment_id = uuid.uuid4()                      # one segment, two languages

    await pipe._translate_and_synthesize(
        segment_id=segment_id, seq=1, speaker=speaker, text="नमस्ते",
        source_lang="hi", target_lang="ur", stt_ms=1.0, capture_ms=1.0)
    await pipe._translate_and_synthesize(
        segment_id=segment_id, seq=1, speaker=speaker, text="नमस्ते",
        source_lang="hi", target_lang="en", stt_ms=1.0, capture_ms=1.0)

    ur_errors = _events(ur.ws, "error")
    assert ur_errors and ur_errors[0]["code"] == "tts_unavailable"
    assert _events(ur.ws, "tts.chunk") == []
    # English is neither suppressed as a "duplicate" nor blamed for Urdu's outage
    assert len(_events(en.ws, "tts.chunk")) == 2
    assert _events(en.ws, "error") == []
    completed = _events(en.ws, "tts.completed")
    assert completed and completed[0]["chunks"] == 2


@pytest.mark.asyncio
async def test_translation_context_keeps_the_room_scoping(session, speaker, no_db,
                                                          monkeypatch):
    """The durable row behind a caption still needs the room, the user and the
    segment — the agent speaks in strings, the database speaks in UUIDs."""
    en = _participant(hear="en")
    _join(session, speaker, en)
    monkeypatch.setattr(P, "ai", FakeAI())
    captured: list = []

    async def fake_translate(db, text, src, tgt, ctx):
        captured.append(ctx)
        return SimpleNamespace(result=_translation_result("Hello", src, tgt))

    monkeypatch.setattr(P, "translate_text", fake_translate)
    pipe = P.MeetingPipeline(session)
    segment_id = uuid.uuid4()

    # A turn is translated with the window the session owner pinned
    # at fan-out time: the speaker's previous turn, never this one.
    pipe.translating.note_source(str(speaker.participant_id), PRIOR_TURN)
    prior = pipe.translating.context_for(str(speaker.participant_id))

    await pipe._translate_and_synthesize(
        segment_id=segment_id, seq=1, speaker=speaker, text="नमस्ते",
        source_lang="hi", target_lang="en", stt_ms=1.0, capture_ms=1.0,
        prev_context=prior)

    ctx = captured[0]
    assert ctx.org_id == session.org_id
    assert ctx.user_id == speaker.user_id          # metering attributes to the speaker
    assert ctx.meeting_id == session.meeting_id
    assert ctx.segment_id == segment_id            # the durable transcript row
    assert ctx.context == PRIOR_TURN      # the prior turn, not this one
    assert ctx.product == "realtime" and ctx.persist and ctx.meter
