"""Tree B failure-injection tests for the fan-out path.

Motivated by the CodeRabbit "State of AI vs. Human Code Generation" report
(2026): AI-authored code shows ~2x more error-handling / exception-path gaps
than human code, and the share-link audio debug hit exactly that class of bug
(a silent MT/TTS failure looked like "translation active" with zero output).

These tests assert the pipeline's degradation contract, per PDD §3 / §89:
- ProviderUnavailable on MT → translation.failed for that target only; the
  canonical transcript and other targets are untouched.
- MT "untranslated_fallback" quality flag → explicit translation.failed to
  caption listeners; TTS never attempted.
- ProviderUnavailable on TTS → quality.degraded(reason=tts_unavailable) to
  audio listeners; translated captions still delivered; meeting survives.
- A target task raising an unexpected exception is isolated by gather — the
  fan-out loop still reports it via translation.failed.
- No listeners needing translation → fanout_skipped diagnostic, no events.

Construction bypasses AudioPipeline.__init__ (VAD, real asyncio loop, DB) and
runs executors inline, so these stay unit-fast with zero external providers.
"""
from __future__ import annotations

import time
import uuid
from types import SimpleNamespace

import pytest

from ai.interfaces import ProviderUnavailable
from globaltalk.realtime import audio_pipeline as ap
from globaltalk.realtime.audio_pipeline import AudioPipeline, Utterance
from globaltalk.realtime.protocol import EventType


# ------------------------------------------------------------------ harness


class _InlineLoop:
    """run_in_executor that calls the function inline (raises propagate)."""

    async def run_in_executor(self, _executor, fn, *args):
        return fn(*args)


class _Recorder:
    """Fake MeetingSession: records every event, routes send/broadcast."""

    def __init__(self, targets: set[str], listeners: list[SimpleNamespace]):
        self.meeting_id = "meet-" + uuid.uuid4().hex[:8]
        self.org_id = "org-1"
        self.events: list[dict] = []
        self.sent: list[tuple[str, dict]] = []  # (participant_id, event)
        self.broadcasts: list[dict] = []
        self.translation_cache: dict = {}
        self._targets = targets
        self._listeners = listeners
        self.participants: dict[str, SimpleNamespace] = {}

    def translation_cache_key(self, segment_id: str, target: str):
        return (segment_id, target)

    def required_target_languages(self, source_language, exclude=None):
        return set(self._targets)

    def listeners_for_language(self, language, *, exclude=None, want_audio=False):
        return [p for p in self._listeners
                if p.listening_language == language and p.participant_id != exclude]

    def record(self, event_type, persist=True, **payload):
        evt = {"type": event_type, "sequence": len(self.events) + 1}
        evt.update(payload)
        self.events.append(evt)
        return evt

    async def send(self, p, evt):
        self.sent.append((p.participant_id, evt))

    async def broadcast(self, evt, **kw):
        self.broadcasts.append(evt)


def _listener(pid: str, *, lang: str = "hi", audio_mode: str = "translated",
              caption_mode: str = "both") -> SimpleNamespace:
    return SimpleNamespace(participant_id=pid, listening_language=lang,
                           audio_mode=audio_mode, caption_mode=caption_mode,
                           connected=True)


def _make_pipeline(targets=None, listeners=None) -> tuple[AudioPipeline, _Recorder]:
    """Assemble an AudioPipeline with the minimal state the fan-out path
    touches. __init__ is skipped: no VAD, no DB, no real loop."""
    targets = targets if targets is not None else {"hi"}
    listeners = listeners if listeners is not None else [_listener("L1")]
    session = _Recorder(targets, listeners)
    pipe = AudioPipeline.__new__(AudioPipeline)
    conn = SimpleNamespace(participant_id="S1", display_name="Speaker",
                           speaking_language="en")
    pipe.session = session
    pipe.conn = conn
    pipe.loop = _InlineLoop()
    pipe._fanout_sem = __import__("asyncio").Semaphore(2)
    pipe._shutdown = False
    # _diag broadcasts via module-level spawn(); silence it in tests.
    pipe._emit_translation_failed = _real_emit(pipe)
    return pipe, session


def _real_emit(pipe):
    """Use the real _emit_translation_failed so tests assert the actual
    event shape produced in production code."""
    import types
    return types.MethodType(AudioPipeline._emit_translation_failed, pipe)


def _utt() -> Utterance:
    now = time.perf_counter()
    uid = uuid.uuid4().hex
    return Utterance(uid=uid, short_id=uid[:16], started_mono_ms=0,
                     t_first_chunk=now, t_stt_final=now)


def _seg_id() -> str:
    return uuid.uuid4().hex


@pytest.fixture(autouse=True)
def _no_spawn(monkeypatch):
    """spawn() schedules fire-and-forget tasks (archive, diag broadcast,
    tts-store). In tests, close the coroutines so no 'never awaited' warnings."""
    def fake_spawn(coro, *, name: str = ""):
        coro.close()
        return None
    monkeypatch.setattr(ap, "spawn", fake_spawn)


def _diag_records(session: _Recorder) -> list[dict]:
    return [e for e in session.events if e["type"] == EventType.DIAGNOSTIC]


# ------------------------------------------------------------------ MT failures


@pytest.mark.asyncio
async def test_mt_provider_unavailable_emits_translation_failed_for_target():
    """`_translate_sync` raising ProviderUnavailable must produce
    translation.failed scoped to that target — never a crash, never silence."""
    pipe, session = _make_pipeline()

    def boom(*_a):
        raise ProviderUnavailable("argos", "no model for en->hi")

    pipe._translate_sync = boom
    sid = _seg_id()
    await pipe._translate_for_language(sid, "en", "hi", "Hello", _utt(), time.perf_counter())

    failed = [e for e in session.events if e["type"] == EventType.TRANSLATION_FAILED]
    assert len(failed) == 1
    assert failed[0]["segment_id"] == sid
    assert failed[0]["target_language"] == "hi"
    assert failed[0]["recoverable"] is True
    # listener routing: the hi-listener received it
    assert session.sent and session.sent[0][0] == "L1"
    assert session.sent[0][1]["type"] == EventType.TRANSLATION_FAILED


@pytest.mark.asyncio
async def test_untranslated_fallback_skips_tts_and_flags_failure():
    """Passthrough/untranslated MT must NOT silently deliver the original
    text as a translation: explicit translation.failed + no TTS attempt."""
    pipe, session = _make_pipeline()
    tts_called = []

    result = SimpleNamespace(text="Hello", provider="passthrough", model="none",
                             confidence=0.0, latency_ms=1.0,
                             quality_flags=["untranslated_fallback"])
    pipe._translate_sync = lambda *_a: result
    pipe._tts_sync = lambda *a: tts_called.append(a) or b""

    sid = _seg_id()
    await pipe._translate_for_language(sid, "en", "hi", "Hello", _utt(), time.perf_counter())

    failed = [e for e in session.events if e["type"] == EventType.TRANSLATION_FAILED]
    assert failed and failed[0]["reason"] == "translation_unavailable"
    assert not any(e["type"] == EventType.TRANSLATION_FINAL for e in session.events)
    assert tts_called == [], "TTS must not run on untranslated fallback"


# ------------------------------------------------------------------ TTS failures


@pytest.mark.asyncio
async def test_tts_unavailable_degrades_to_captions_only():
    """TTS ProviderUnavailable → quality.degraded(tts_unavailable) to audio
    listeners; the translated caption itself must still arrive."""
    listeners = [_listener("L1", audio_mode="translated", caption_mode="translated")]
    pipe, session = _make_pipeline(listeners=listeners)

    result = SimpleNamespace(text="नमस्ते", provider="argos", model="en_hi",
                             confidence=0.8, latency_ms=12.0, quality_flags=[])
    pipe._translate_sync = lambda *_a: result
    pipe._persist_translation = lambda *_a: "tr-" + uuid.uuid4().hex

    def boom(*_a):
        raise ProviderUnavailable("piper", "voice hi not installed")

    pipe._tts_sync = boom

    sid = _seg_id()
    await pipe._translate_for_language(sid, "en", "hi", "Hello", _utt(), time.perf_counter())

    degraded = [e for e in session.events if e["type"] == EventType.QUALITY_DEGRADED]
    assert len(degraded) == 1
    assert degraded[0]["reason"] == "tts_unavailable"
    assert degraded[0]["recoverable"] is True
    captions = [e for e in session.events if e["type"] == EventType.TRANSLATION_FINAL]
    assert len(captions) == 1 and captions[0]["text"] == "नमस्ते"
    assert not any(e["type"] == EventType.TTS_COMPLETED for e in session.events)


# ------------------------------------------------------------------ happy path


@pytest.mark.asyncio
async def test_mt_and_tts_success_delivers_wav_audio_and_latency():
    """Positive control: with healthy MT + TTS, audio listeners receive a
    TTS_COMPLETED (wav) and quality.latency — proving the failure tests above
    assert absence, not a broken harness."""
    listeners = [_listener("L1", audio_mode="translated", caption_mode="translated")]
    pipe, session = _make_pipeline(listeners=listeners)

    result = SimpleNamespace(text="नमस्ते", provider="argos", model="en_hi",
                             confidence=0.9, latency_ms=10.0, quality_flags=[])
    pipe._translate_sync = lambda *_a: result
    pipe._persist_translation = lambda *_a: "tr-fixed"
    pipe._tts_sync = lambda *_a: b"RIFFfake-wav-bytes"

    sid = _seg_id()
    await pipe._translate_for_language(sid, "en", "hi", "Hello", _utt(), time.perf_counter())

    tts = [e for e in session.events if e["type"] == EventType.TTS_COMPLETED]
    assert len(tts) == 1
    assert tts[0]["audio_format"] == "wav"
    assert tts[0]["synthetic"] is True
    lat = [e for e in session.events if e["type"] == EventType.QUALITY_LATENCY]
    assert len(lat) == 1
    assert "total_e2e_latency_ms" in lat[0]


# ------------------------------------------------------------------ fan-out loop


@pytest.mark.asyncio
async def test_fanout_isolates_unexpected_target_exception():
    """A non-ProviderUnavailable crash in one target is swallowed by gather,
    reported via translation.failed, and never aborts the fan-out."""
    listeners = [_listener("L1", lang="hi"), _listener("L2", lang="mr")]
    pipe, session = _make_pipeline(targets={"hi", "mr"}, listeners=listeners)

    def flaky(text, source, target):
        if target == "hi":
            raise RuntimeError("boom in mt worker")
        return SimpleNamespace(text="ok-" + target, provider="argos", model="m",
                               confidence=0.7, latency_ms=5.0, quality_flags=[])

    pipe._translate_sync = flaky
    pipe._persist_translation = lambda *_a: "tr-x"
    pipe._tts_sync = lambda *_a: b"RIFFw"

    sid = _seg_id()
    await pipe._fanout(sid, "en", "Hello", _utt(), time.perf_counter())  # must not raise

    failed = [e for e in session.events if e["type"] == EventType.TRANSLATION_FAILED]
    assert any(e["target_language"] == "hi" for e in failed)
    ok = [e for e in session.events if e["type"] == EventType.TRANSLATION_FINAL]
    assert any(e["target_language"] == "mr" for e in ok), "healthy target unaffected"


@pytest.mark.asyncio
async def test_fanout_skips_when_no_target_listeners_and_emits_diagnostic():
    """Everyone hears the source language → no TRANSLATION_STARTED at all,
    and the new fanout_skipped diagnostic records WHY (the observability
    gap that made the original debug silent)."""
    pipe, session = _make_pipeline(targets=set())
    sid = _seg_id()
    await pipe._fanout(sid, "en", "Hello", _utt(), time.perf_counter())

    assert not any(e["type"] == EventType.TRANSLATION_STARTED for e in session.events)
    skips = [d for d in _diag_records(session) if d.get("stage") == "fanout_skipped"]
    assert len(skips) == 1
    assert skips[0]["reason"] == "no_listeners_needing_translation"
    assert skips[0]["segment_id"] == sid


@pytest.mark.asyncio
async def test_fanout_diagnostic_records_provider_stages(monkeypatch):
    """The mt_enter / mt_exit diagnostics carry the provider name so the
    frontend banner can show 'MT: argos' — a real provider, not a dev stub."""
    diag_events: list[dict] = []
    listeners = [_listener("L1")]
    pipe, session = _make_pipeline(listeners=listeners)
    orig_record = session.record

    def rec(event_type, persist=True, **payload):
        evt = orig_record(event_type, persist=persist, **payload)
        if event_type == EventType.DIAGNOSTIC:
            diag_events.append(evt)
        return evt

    session.record = rec
    result = SimpleNamespace(text="नमस्ते", provider="argos", model="en_hi",
                             confidence=0.9, latency_ms=8.0, quality_flags=[])
    pipe._translate_sync = lambda *_a: result
    pipe._persist_translation = lambda *_a: "tr-y"
    pipe._tts_sync = lambda *_a: b"RIFFw"

    await pipe._fanout(_seg_id(), "en", "Hello", _utt(), time.perf_counter())

    stages = {d["stage"]: d for d in diag_events}
    assert "fanout_start" in stages and stages["fanout_start"]["targets"] == ["hi"]
    assert "mt_enter" in stages and "mt_exit" in stages
    assert stages["mt_exit"]["provider"] == "argos"
    assert "tts_enter" in stages and "tts_first_audio" in stages
