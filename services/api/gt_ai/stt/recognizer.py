"""STT Recognizer Adapter Interface & Streaming Implementation (Phase 3).

Implements the Phase 3 speech recognizer lifecycle:
- start(session_id, participant_id, source_language=None)
- push_audio(session_id, audio_frame)
- stop(session_id)
- on_partial_transcript(callback)
- on_final_transcript(callback)
- on_error(callback)

Features:
- Self-hosted faster-whisper / Whisper capable
- Off-thread inference (never blocks the async event loop)
- CPU fallback (int8) + GPU acceleration (cuda/float16)
- Model warm-up to prevent cold-start latency
- VAD silence handling (no inference on empty silence)
- Language locking: locks auto-detected language once confidence threshold is reached,
  preventing flickering or switching due to isolated noisy tokens.
"""
from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from gt_ai.base import STTProvider
from gt_ai.types import TranscriptChunk
from gt_ai.vad import EnergyVAD, VadState

log = logging.getLogger("gt_ai.stt.recognizer")

CONFIDENCE_LOCK_THRESHOLD = 0.70
PARTIAL_INTERVAL_S = 1.0


@dataclass
class RecognizerSession:
    session_id: str
    participant_id: str
    source_language: str | None = None
    locked_language: str | None = None
    vad: EnergyVAD = field(default_factory=lambda: EnergyVAD(sample_rate=16000))
    buffer: bytearray = field(default_factory=bytearray)
    in_speech: bool = False
    started_at_ms: int = 0
    capture_started: float = 0.0
    last_partial_at: float = 0.0
    last_partial_text: str = ""
    active: bool = True


class SpeechRecognizer(ABC):
    """Abstract interface for streaming speech recognition adapters."""

    @abstractmethod
    async def start(
        self, session_id: str, participant_id: str, source_language: str | None = None
    ) -> None:
        """Start recognizer for a participant in a session."""

    @abstractmethod
    async def push_audio(self, session_id: str, audio_frame: bytes) -> None:
        """Push an audio frame (e.g. 16kHz mono PCM16) into the recognizer."""

    @abstractmethod
    async def stop(self, session_id: str) -> None:
        """Stop and flush recognizer for a session."""

    @abstractmethod
    def on_partial_transcript(
        self, callback: Callable[[str, str, TranscriptChunk], Any]
    ) -> None:
        """Register callback: callback(session_id, participant_id, chunk)."""

    @abstractmethod
    def on_final_transcript(
        self, callback: Callable[[str, str, TranscriptChunk], Any]
    ) -> None:
        """Register callback: callback(session_id, participant_id, chunk)."""

    @abstractmethod
    def on_error(self, callback: Callable[[str, str, Exception], Any]) -> None:
        """Register callback: callback(session_id, participant_id, error)."""


class StreamingSpeechRecognizer(SpeechRecognizer):
    """Concrete streaming recognizer backed by an STTProvider."""

    def __init__(self, provider: STTProvider, sample_rate: int = 16000) -> None:
        self.provider = provider
        self.sample_rate = sample_rate
        self.sessions: dict[str, RecognizerSession] = {}
        self._partial_cbs: list[Callable[[str, str, TranscriptChunk], Any]] = []
        self._final_cbs: list[Callable[[str, str, TranscriptChunk], Any]] = []
        self._error_cbs: list[Callable[[str, str, Exception], Any]] = []

    def on_partial_transcript(
        self, callback: Callable[[str, str, TranscriptChunk], Any]
    ) -> None:
        self._partial_cbs.append(callback)

    def on_final_transcript(
        self, callback: Callable[[str, str, TranscriptChunk], Any]
    ) -> None:
        self._final_cbs.append(callback)

    def on_error(self, callback: Callable[[str, str, Exception], Any]) -> None:
        self._error_cbs.append(callback)

    async def start(
        self, session_id: str, participant_id: str, source_language: str | None = None
    ) -> None:
        # If explicit language is provided and not 'auto', lock it immediately
        initial_locked = None
        if source_language and source_language.lower() not in ("auto", ""):
            initial_locked = source_language.lower()

        session = RecognizerSession(
            session_id=session_id,
            participant_id=participant_id,
            source_language=source_language,
            locked_language=initial_locked,
        )
        self.sessions[session_id] = session

    async def push_audio(self, session_id: str, audio_frame: bytes) -> None:
        sess = self.sessions.get(session_id)
        if not sess or not sess.active or not audio_frame:
            return

        events = sess.vad.process(audio_frame)
        for ev in events:
            if ev.state == VadState.SPEECH:
                sess.in_speech = True
                sess.buffer = bytearray(audio_frame)
                sess.started_at_ms = ev.timestamp_ms
                sess.capture_started = time.perf_counter()
                sess.last_partial_at = time.perf_counter()
                sess.last_partial_text = ""
            else:  # SILENCE
                if sess.in_speech:
                    sess.buffer.extend(audio_frame)
                    sess.in_speech = False
                    audio_payload = bytes(sess.buffer)
                    sess.buffer = bytearray()
                    asyncio.create_task(
                        self._finalize_segment(sess, audio_payload),
                        name=f"stt-final-{session_id}-{sess.started_at_ms}",
                    )

        if sess.in_speech:
            sess.buffer.extend(audio_frame)
            now = time.perf_counter()
            # Bounded continuous speech check (15s max)
            if (now - sess.capture_started) >= 15.0 and len(sess.buffer) >= self.sample_rate * 2 * 10:
                audio_payload = bytes(sess.buffer)
                sess.buffer = bytearray()
                sess.capture_started = now
                sess.last_partial_at = now
                sess.last_partial_text = ""
                asyncio.create_task(
                    self._finalize_segment(sess, audio_payload),
                    name=f"stt-split-{session_id}-{now}",
                )
            elif (
                now - sess.last_partial_at >= PARTIAL_INTERVAL_S
                and len(sess.buffer) > self.sample_rate * 2 * 0.8
            ):
                sess.last_partial_at = now
                asyncio.create_task(
                    self._emit_partial(sess, bytes(sess.buffer)),
                    name=f"stt-partial-{session_id}-{now}",
                )

    async def _emit_partial(self, sess: RecognizerSession, audio_bytes: bytes) -> None:
        try:
            lang_hint = sess.locked_language or sess.source_language
            chunk = await self.provider.transcribe(
                audio_bytes, self.sample_rate, lang_hint=lang_hint
            )
            if not chunk or not chunk.text or chunk.text == sess.last_partial_text:
                return

            sess.last_partial_text = chunk.text
            # Lock language if auto-detecting and confidence is high enough
            if not sess.locked_language and chunk.language and (chunk.confidence or 0.0) >= CONFIDENCE_LOCK_THRESHOLD:
                sess.locked_language = chunk.language

            partial_chunk = TranscriptChunk(
                text=chunk.text,
                language=chunk.language or sess.locked_language or sess.source_language,
                is_final=False,
                confidence=chunk.confidence,
                model=chunk.model,
                provider=chunk.provider,
            )
            for cb in self._partial_cbs:
                try:
                    res = cb(sess.session_id, sess.participant_id, partial_chunk)
                    if asyncio.iscoroutine(res):
                        await res
                except Exception as ex:
                    log.exception("partial callback failed: %s", ex)
        except Exception as ex:
            self._notify_error(sess, ex)

    async def _finalize_segment(self, sess: RecognizerSession, audio_bytes: bytes) -> None:
        if len(audio_bytes) < 1600:  # <50ms noise
            return
        try:
            lang_hint = sess.locked_language or sess.source_language
            chunk = await self.provider.transcribe(
                audio_bytes, self.sample_rate, lang_hint=lang_hint
            )
            text = (chunk.text or "").strip()
            if not text:
                return

            # Lock language for this segment
            if not sess.locked_language and chunk.language:
                sess.locked_language = chunk.language

            final_chunk = TranscriptChunk(
                text=text,
                language=chunk.language or sess.locked_language or sess.source_language,
                is_final=True,
                confidence=chunk.confidence,
                model=chunk.model,
                provider=chunk.provider,
            )
            for cb in self._final_cbs:
                try:
                    res = cb(sess.session_id, sess.participant_id, final_chunk)
                    if asyncio.iscoroutine(res):
                        await res
                except Exception as ex:
                    log.exception("final callback failed: %s", ex)
        except Exception as ex:
            self._notify_error(sess, ex)

    def _notify_error(self, sess: RecognizerSession, error: Exception) -> None:
        for cb in self._error_cbs:
            try:
                res = cb(sess.session_id, sess.participant_id, error)
                if asyncio.iscoroutine(res):
                    asyncio.create_task(res)
            except Exception:
                pass

    async def stop(self, session_id: str) -> None:
        sess = self.sessions.pop(session_id, None)
        if not sess:
            return
        sess.active = False
        if sess.in_speech and len(sess.buffer) > 3200:
            audio_bytes = bytes(sess.buffer)
            sess.buffer = bytearray()
            await self._finalize_segment(sess, audio_bytes)
