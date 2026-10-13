"""Phase 3 — what each listener hears, and what happens when they change it.

The acceptance matrix says modes must have "no unintended mixing or duplicate
audio", and the exit gate says an interruption may not leave stale or duplicated
output behind. Both are statements about *routing*, and routing used to be
decided once per utterance: ``listeners_for_language`` ran before TTS started and
every chunk of that utterance went to that frozen list. So a listener who
switched language mid-stream kept hearing the language they had just left, and
nothing on the wire told their browser to stop.

These tests drive the real ``MeetingPipeline`` delivery path and the real
``SessionManager`` routing with fake providers. Evidence level: integration of
the server's routing layer — not a browser test, and not a human listening check.
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
    def __init__(self, tts_chunks: int = 2, chunk_delay: float = 0.0) -> None:
        self.tts_chunks = tts_chunks
        self.chunk_delay = chunk_delay

    async def transcribe(self, audio: bytes, sample_rate: int,
                         lang_hint: str | None = None):
        return (TranscriptChunk(text="नमस्ते", language="hi", is_final=True,
                                confidence=0.9, model="fake-stt", provider="fake"),
                _decision("fake-stt", "stt"))

    async def detect_language(self, text: str) -> DetectionResult:
        return DetectionResult(language="hi", confidence=0.88, provider="fake-detect")

    async def synthesize_stream(self, text: str, lang: str, voice: str | None = None):
        async def stream():
            for _ in range(self.tts_chunks):
                # A real provider paces its chunks; without a gap here the whole
                # run would finish before a test could interrupt it.
                await asyncio.sleep(self.chunk_delay)
                yield AudioChunk(data=b"\x54\x48" * 80, sample_rate=24000,
                                 encoding="pcm_s16le", format="wav",
                                 provider="fake-tts", model="fake-tts-m",
                                 duration_ms=250.0)
        return stream(), _decision("fake-tts", "tts")

    def is_dev_mode(self, task) -> bool:
        return True


def _participant(*, hear: str, mode: str = "translated", speak: str = "auto",
                 captions: bool = True, name: str = "") -> RtParticipant:
    return RtParticipant(participant_id=uuid.uuid4(), user_id=uuid.uuid4(),
                         display_name=name or f"p-{hear}",
                         speak_lang=speak, hear_lang=hear, audio_mode=mode,
                         captions_enabled=captions, ws=FakeWs(), connected=True)


@pytest.fixture
def session():
    return RtSession(session_id="sess-mode", meeting_id=uuid.uuid4(),
                     org_id=uuid.uuid4(), room_name="room", mode="ws")


@pytest.fixture
def no_db(monkeypatch):
    @asynccontextmanager
    async def _fake_session(*_a, **_kw):
        yield SimpleNamespace(add=lambda *_: None, commit=lambda: None,
                              execute=lambda *_: None)
    monkeypatch.setattr(P, "db_session", _fake_session)


def _join(session: RtSession, *participants: RtParticipant) -> None:
    for p in participants:
        manager.add_participant(session, p)


def _events(ws: FakeWs, event_type: str) -> list[dict]:
    return [e for e in ws.events if e.get("type") == event_type]


def _chunks(ws: FakeWs) -> int:
    """Chunks on both transports; the client dedups them into one play queue."""
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


def _pipe(session: RtSession, monkeypatch, *, tts_chunks: int = 2,
          chunk_delay: float = 0.0) -> P.MeetingPipeline:
    monkeypatch.setattr(P, "ai", FakeAI(tts_chunks=tts_chunks,
                                        chunk_delay=chunk_delay))
    _fake_translate(monkeypatch)
    return P.MeetingPipeline(session)


async def _deliver(pipe: P.MeetingPipeline, speaker: RtParticipant, *,
                   target_lang: str = "en", seq: int = 1) -> str:
    """Run one language group to completion, exactly as the fan-out does."""
    corr = str(uuid.uuid4())
    await pipe._translate_and_synthesize(
        segment_id=uuid.uuid4(), seq=seq, speaker=speaker, text="नमस्ते",
        source_lang="hi", target_lang=target_lang, stt_ms=1.0, capture_ms=1.0,
        utterance_id=corr)
    return corr


async def _wait_for(predicate, what: str, timeout: float = 2.0) -> None:
    deadline = time.perf_counter() + timeout
    while not predicate():
        if time.perf_counter() > deadline:
            pytest.fail(f"timed out waiting for {what}")
        await asyncio.sleep(0.005)


# --------------------------------------------------------------------------- #
# The matrix: audio_mode decides what a listener hears
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
@pytest.mark.parametrize(("audio_mode", "hears_audio"), [
    ("translated", True),    # only the synthesized voice
    ("mixed", True),          # real voice and synthesized voice together
    ("original", False),      # never the synthesized voice
])
async def test_audio_mode_decides_whether_synthesized_speech_is_delivered(
        session, no_db, monkeypatch, audio_mode, hears_audio):
    a = _participant(hear="hi", speak="hi")
    listener = _participant(hear="en", mode=audio_mode)
    _join(session, a, listener)
    pipe = _pipe(session, monkeypatch)

    await _deliver(pipe, a)

    assert bool(_events(listener.ws, "tts.chunk")) is hears_audio
    assert bool(listener.ws.frames) is hears_audio
    # A caption is not audio: every mode keeps its text.
    assert len(_events(listener.ws, "translation.final")) == 1


@pytest.mark.asyncio
async def test_original_relay_reaches_original_and_mixed_but_never_the_sender(
        session):
    """The human conversation has to survive with the AI path fully down, so the
    relay is the one path that must not depend on translation at all — and it
    must not echo a speaker's own microphone back to them."""
    a = _participant(hear="hi", mode="original", speak="hi")
    original = _participant(hear="en", mode="original")
    mixed = _participant(hear="en", mode="mixed")
    translated = _participant(hear="en", mode="translated")
    _join(session, a, original, mixed, translated)

    await manager.relay_audio(session, a.participant_id, b"\x01\x02" * 80)

    assert len(a.ws.frames) == 0
    assert len(original.ws.frames) == 1
    assert len(mixed.ws.frames) == 1
    assert len(translated.ws.frames) == 0


@pytest.mark.asyncio
async def test_captions_do_not_depend_on_audio_mode(session, no_db, monkeypatch):
    """A listener who wants text only must still cause the translation to exist —
    otherwise turning off your voice turns off everybody's captions."""
    a = _participant(hear="hi", speak="hi")
    text_only = _participant(hear="en", mode="original", captions=True)
    _join(session, a, text_only)
    pipe = _pipe(session, monkeypatch)

    targets = manager.required_target_languages(
        session, "hi", exclude_speaker=str(a.participant_id))
    assert targets == {"en"}

    await _deliver(pipe, a)
    assert len(_events(text_only.ws, "translation.final")) == 1
    assert _chunks(text_only.ws) == 0


# --------------------------------------------------------------------------- #
# No duplicate audio
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_two_listeners_sharing_a_language_each_get_the_run_exactly_once(
        session, no_db, monkeypatch):
    a = _participant(hear="hi", speak="hi")
    en1 = _participant(hear="en", mode="translated")
    en2 = _participant(hear="en", mode="mixed")
    _join(session, a, en1, en2)
    pipe = _pipe(session, monkeypatch, tts_chunks=3)

    await _deliver(pipe, a)

    # One translation per language for the whole room, however many want it.
    # Each socket gets one JSON chunk and one binary chunk per TTS chunk, which
    # the client folds into a single play queue — never two voices.
    assert _chunks(en1.ws) == 6
    assert _chunks(en2.ws) == 6
    recipients = pipe._audio_recipients("en", a.participant_id)
    assert {str(p.participant_id) for p in recipients} == {str(en1.participant_id),
                                                            str(en2.participant_id)}


@pytest.mark.asyncio
async def test_a_speaker_is_never_in_their_own_translated_audio_group(
        session, no_db, monkeypatch):
    """Feedback-loop guard, at delivery rather than only at target selection.

    ``required_target_languages`` skips self-translation, but when a language
    group exists for somebody else, the plain ``hear_lang`` match used to put
    the speaker inside it too — playing their own voice back at them, translated,
    straight into the microphone that is still open.
    """
    a = _participant(hear="en", mode="translated", speak="hi")
    b = _participant(hear="en", mode="translated")
    _join(session, a, b)
    pipe = _pipe(session, monkeypatch)

    await _deliver(pipe, a)

    assert _chunks(b.ws) == 4
    assert _chunks(a.ws) == 0
    # The speaker still reads the translation, they just do not hear it.
    assert len(_events(a.ws, "translation.final")) == 1


# --------------------------------------------------------------------------- #
# Changing your mind mid-utterance
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_switching_language_stops_the_old_language_for_that_listener_only(
        session, no_db, monkeypatch):
    a = _participant(hear="hi", speak="hi")
    switcher = _participant(hear="en", mode="translated")
    stay = _participant(hear="en", mode="translated")
    _join(session, a, switcher, stay)
    pipe = _pipe(session, monkeypatch, tts_chunks=20, chunk_delay=0.02)
    corr = str(uuid.uuid4())

    task = asyncio.create_task(pipe._translate_and_synthesize(
        segment_id=uuid.uuid4(), seq=1, speaker=a, text="नमस्ते", source_lang="hi",
        target_lang="en", stt_ms=1.0, capture_ms=1.0, utterance_id=corr))
    await _wait_for(lambda: _events(switcher.ws, "tts.chunk"),
                    "the first chunk of the run")

    await pipe.recipient_changed(switcher.participant_id,
                                 previous_language="en", new_language="ur")
    switched_at = len(_events(switcher.ws, "tts.chunk"))
    await asyncio.wait_for(task, 5)

    assert 0 < switched_at < 20, f"the whole 20-chunk run played anyway: {switched_at}"
    assert len(_events(switcher.ws, "tts.chunk")) == switched_at, \
        "chunks kept arriving after the listener left the language"
    assert _events(stay.ws, "tts.chunk"), "the listener who stayed lost their audio"
    assert len(_events(stay.ws, "tts.chunk")) == 20
    assert len(stay.ws.frames) == 20

    flushes = _events(switcher.ws, "playback.flush")
    assert len(flushes) == 1
    assert flushes[0]["scope"] == "recipient"
    assert flushes[0]["reason"] == "language_changed"
    assert flushes[0]["previous_language"] == "en"
    assert flushes[0]["new_language"] == "ur"
    # Scoped three ways: not to the other listener, and not to the replay buffer,
    # where a reconnecting *different* participant would pick it up.
    assert _events(stay.ws, "playback.flush") == []
    assert [raw for raw in session.replay_buffer
            if json.loads(raw).get("type") == "playback.flush"] == []


@pytest.mark.asyncio
async def test_switching_back_to_a_language_resumes_delivery(
        session, no_db, monkeypatch):
    """en→ur→en used to leave (listener, "en") stale forever: the first switch
    marked it and nothing un-marked it, so that listener never heard English
    again for the rest of the meeting."""
    a = _participant(hear="hi", speak="hi")
    listener = _participant(hear="en", mode="translated")
    _join(session, a, listener)
    pipe = _pipe(session, monkeypatch)

    await pipe.recipient_changed(listener.participant_id,
                                 previous_language="en", new_language="ur")
    await pipe.recipient_changed(listener.participant_id,
                                 previous_language="ur", new_language="en")

    await _deliver(pipe, a)
    assert _chunks(listener.ws) == 4


@pytest.mark.asyncio
async def test_a_language_change_leaves_another_listeners_run_untouched(
        session, no_db, monkeypatch):
    a = _participant(hear="hi", speak="hi")
    ur_listener = _participant(hear="ur", mode="translated")
    switcher = _participant(hear="en", mode="translated")
    _join(session, a, ur_listener, switcher)
    pipe = _pipe(session, monkeypatch, tts_chunks=3)

    await pipe.recipient_changed(switcher.participant_id,
                                 previous_language="en", new_language="ur")
    await _deliver(pipe, a, target_lang="en")
    await _deliver(pipe, a, target_lang="ur")

    assert _chunks(switcher.ws) == 0
    assert _chunks(ur_listener.ws) == 6
