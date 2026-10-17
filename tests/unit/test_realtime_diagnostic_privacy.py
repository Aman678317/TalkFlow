"""Phase 4: the meeting's diagnostic stream must not carry what was said.

Phase 4 asks for privacy-safe stage events — "event IDs, sequence numbers, stage
timings, payload lengths, language codes and sanitized error codes" — and for
avoiding logging raw audio and transcripts. P4-a built the structured record and
pinned the *names* it may carry. What nobody pinned was what a record must not
carry, and the code answers that question in the worst available way:

    text_preview=segment.recognized_text[:80]           # stt_exit
    text_preview=text[:80]                              # fanout_start, mt_enter
    translated_text_preview=translated[:80]             # mt_exit
    error=str(e)[:160]                                  # every failure stage

Those four fields ride on a `diagnostic` event that `_broadcast_diag` sends to
**every connected participant**, gated by nothing — not a flag, not a role, not
an operator setting. So in a meeting where Aman speaks and four people listen,
every listener who is not entitled to the caption still receives the first
eighty characters of it, and a provider that quotes the offending sentence back
in its error hands the same words to the whole room. The listener's own caption
arrives later, scoped to them, through a path that was written carefully; the
diagnostic stream bypasses all of it.

These tests drive a real turn through the real stage bodies and assert one rule:
**a diagnostic record may describe the pipeline, never the content.** Lengths,
providers, models, timings, language codes and error class names are all about
the machine. Words are not.

Evidence level: the real ``MeetingPipeline`` stage bodies, the real
``TranslationAgent`` and ``RealtimeTranslatorProvider``, the real session
manager; fake providers and a fake database session.
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
    AudioChunk, DetectionResult, RouteDecision, TranscriptChunk,
    TranslationResult,
)

import app.realtime.pipeline as P
from app.errors import ProviderError
from app.realtime.session_manager import RtParticipant, RtSession, manager

# 1000 ms of 16 kHz mono PCM16: exactly 32 000 bytes.
AUDIO_1S = b"\x01\x02" * 16_000

#: Words that must never appear on a diagnostic record. A sentence long enough
#: to be worth leaking, with a distinct fragment ("मौसम") so a test can tell a
#: full copy from a partial one.
SPOKEN = "नमस्ते, आज मौसम बहुत अच्छा है"


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
    async def transcribe(self, audio: bytes, sample_rate: int,
                         lang_hint: str | None = None):
        return (TranscriptChunk(text=SPOKEN, language="hi", is_final=True,
                                confidence=0.9, model="fake-stt",
                                provider="fake"),
                _decision("fake-stt", "stt"))

    async def detect_language(self, text: str) -> DetectionResult:
        return DetectionResult(language="hi", confidence=0.88,
                               provider="fake-detect")

    async def synthesize_stream(self, text: str, lang: str,
                                voice: str | None = None):
        async def stream():
            yield AudioChunk(data=b"\x54\x48" * 80, sample_rate=24000,
                             encoding="pcm_s16le", format="wav",
                             provider="fake-tts", model="fake-tts-m",
                             duration_ms=250.0)
        return stream(), _decision("fake-tts", "tts")

    def is_dev_mode(self, task) -> bool:
        return True


def _participant(*, hear: str, speak: str = "hi", mode: str = "translated",
                 name: str = "p") -> RtParticipant:
    return RtParticipant(participant_id=uuid.uuid4(), user_id=uuid.uuid4(),
                         display_name=name, speak_lang=speak, hear_lang=hear,
                         audio_mode=mode, captions_enabled=True,
                         ws=FakeWs(), connected=True)


@pytest.fixture
def session():
    return RtSession(session_id="sess-diag", meeting_id=uuid.uuid4(),
                     org_id=uuid.uuid4(), room_name="room", mode="ws")


@pytest.fixture
def no_db(monkeypatch):
    @asynccontextmanager
    async def _fake_session(*_a, **_kw):
        def _add(obj):
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

        async def _execute(*_a, **_kw):
            return SimpleNamespace(scalar=lambda: 0)

        async def _commit():
            return None

        yield SimpleNamespace(add=_add, commit=_commit, execute=_execute)
    monkeypatch.setattr(P, "db_session", _fake_session)
    monkeypatch.setattr(P.settings, "retention_audio_days", 0, raising=False)


@pytest.fixture
def speaker():
    return _participant(hear="hi", mode="original", name="Aman")


@pytest.fixture
def listener():
    """Hears English, so the turn really does fan out and reach `mt_exit`."""
    return _participant(hear="en", name="Beth")


def _diags(*wss: FakeWs) -> list[dict]:
    """Every diagnostic record any of these sockets was sent."""
    return [e["data"] for ws in wss for e in ws.events
            if e.get("type") == "diagnostic"]


def _translating(monkeypatch, *, fail_with: Exception | None = None):
    """A translation service, so `mt_enter`/`mt_exit` both run."""
    if fail_with is not None:
        async def translate(db, text, src, tgt, ctx):
            raise fail_with
    else:
        async def translate(db, text, src, tgt, ctx):
            return SimpleNamespace(result=TranslationResult(
                text=f"Hello, the weather today is very good. ({text})",
                source_lang=src, target_lang=tgt, model="fake-mt",
                provider="fake-mt", latency_ms=5.0, quality_flags=[]))
    monkeypatch.setattr(P, "translate_text", translate)


async def _turn(pipe: P.MeetingPipeline, speaker: RtParticipant) -> None:
    u = P.UtteranceState(
        participant_id=speaker.participant_id,
        capture_started=time.perf_counter() - 1.0,
        started_at_ms=0, seq=1, in_speech=False)
    await pipe._finalize_utterance(
        speaker, u, audio_bytes=AUDIO_1S, start_ms=0,
        capture_started=u.capture_started, utterance_id=uuid.uuid4(), seq=1)
    deadline = time.time() + 10.0
    while pipe.translation_tasks and time.time() < deadline:
        await asyncio.gather(*list(pipe.translation_tasks.values()),
                             return_exceptions=True)



# --------------------------------------------------------------------------- #
# the rule
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_a_successful_turn_leaks_no_words_into_the_room(
        session, speaker, listener, no_db, monkeypatch):
    """The whole turn, stage by stage, with nothing said in the stages.

    Both sockets are checked because the leak is not directional: the speaker
    sees their own words come back off the diagnostic stream, and every listener
    sees the first eighty characters before the caption logic has decided they
    are allowed to.
    """
    manager.add_participant(session, speaker)
    manager.add_participant(session, listener)
    monkeypatch.setattr(P, "ai", FakeAI())
    _translating(monkeypatch)

    await _turn(P.MeetingPipeline(session), speaker)

    records = _diags(speaker.ws, listener.ws)
    assert records, "the turn produced no diagnostic records at all"
    for rec in records:
        blob = json.dumps(rec, ensure_ascii=False)
        assert SPOKEN not in blob, rec
        assert "मौसम" not in blob, rec
        assert "weather" not in blob.lower(), rec


@pytest.mark.asyncio
async def test_no_diagnostic_record_carries_a_content_field_at_all(
        session, speaker, listener, no_db, monkeypatch):
    """Named fields, not just a substring scan.

    A key called `text_preview` invites the next reader to assume it is safe to
    fill in; it is the field this test exists to keep empty of content.
    """
    manager.add_participant(session, speaker)
    manager.add_participant(session, listener)
    monkeypatch.setattr(P, "ai", FakeAI())
    _translating(monkeypatch)

    await _turn(P.MeetingPipeline(session), speaker)

    banned = {"text_preview", "translated_text_preview", "text",
              "translated_text", "source_text", "error"}
    for rec in _diags(speaker.ws, listener.ws):
        assert banned.isdisjoint(rec), rec


@pytest.mark.asyncio
async def test_a_provider_that_quotes_the_sentence_still_does_not_reach_the_room(
        session, speaker, listener, no_db, monkeypatch):
    """Errors are the second leak, and the sneakier one.

    Engines quote what they refused. A sanitizer that only strips the caption
    fields would pass the test above and fail this one.
    """
    manager.add_participant(session, speaker)
    manager.add_participant(session, listener)
    monkeypatch.setattr(P, "ai", FakeAI())
    _translating(monkeypatch, fail_with=ProviderError(
        f"Provider refused this text as out of domain: {SPOKEN!r}"))

    await _turn(P.MeetingPipeline(session), speaker)

    failed = [r for r in _diags(speaker.ws, listener.ws)
              if str(r.get("stage", "")).endswith("failed")]
    assert failed, "a refused translation produced no failure record"
    for rec in failed:
        blob = json.dumps(rec, ensure_ascii=False)
        assert "मौसम" not in blob, rec
        # The stage still says what kind of thing went wrong, which is the whole
        # point of keeping the record.
        assert rec.get("error_type"), rec


# --------------------------------------------------------------------------- #
# what the stream is for, and must keep being for
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_the_stream_still_describes_the_pipeline(
        session, speaker, listener, no_db, monkeypatch):
    """Privacy is not an excuse for blindness.

    The banner in the browser reads `stage`, `provider` and `reason` to tell a
    user whether a real model answered or a dev stand-in did — the specific
    thing that made this stream worth building in P4-a. Stripping content has to
    leave all of that, and the payload length, in place.
    """
    manager.add_participant(session, speaker)
    manager.add_participant(session, listener)
    monkeypatch.setattr(P, "ai", FakeAI())
    _translating(monkeypatch)

    await _turn(P.MeetingPipeline(session), speaker)

    records = _diags(speaker.ws, listener.ws)
    stages = {r.get("stage") for r in records}
    assert "stt_exit" in stages and "mt_enter" in stages and "mt_exit" in stages

    entered = [r for r in records if r.get("stage") == "mt_enter"][-1]
    assert entered["source_lang"] == "hi" and entered["target_lang"] == "en"
    assert entered["text_len"] == len(SPOKEN), (
        "the length is the privacy-safe replacement for the preview")

    exited = [r for r in records if r.get("stage") == "stt_exit"][-1]
    assert exited["provider"] == "fake" and exited["model"] == "fake-stt"
    assert exited["text_len"] == len(SPOKEN)
