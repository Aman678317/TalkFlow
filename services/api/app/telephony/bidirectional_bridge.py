"""Bidirectional Speech Translation Bridge for International Phone Calling.

Implements two concurrent independent translation pipelines:
- Direction A -> B: Caller Audio -> VAD -> STT -> Language Detect -> MT -> TTS -> Receiver Audio
- Direction B -> A: Receiver Audio -> VAD -> STT -> Language Detect -> MT -> TTS -> Caller Audio

Features:
- Sentence/phrase boundary detection via SentenceChunker
- Low-latency waterfall metrics tracking (Speech -> STT -> MT -> TTS -> E2E)
- Instant barge-in / speech interruption with carrier buffer clearing
- AI Voice Agent mode using composed prompt version
- Resilient non-blocking error handling (degradation notice without dropping call)
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from app.ai import ai
from app.config import settings
from app.db import models as M
from app.db.base import utcnow
from app.db.session import db_session
from app.errors import AppError, ProviderError
from app.telephony.audio_codec import (
    mulaw_to_pcm16,
    pcm16_to_mulaw,
    resample_8k_to_16k,
    resample_to_8k,
)
from app.telephony.sentence_chunker import SentenceChunker
from gt_ai.types import Intent, Task, TranslationRequest
from gt_ai.vad import EnergyVAD, VadState, create_vad

log = logging.getLogger("app.telephony.bridge")


@dataclass
class StageTiming:
    """Latency breakdown for an individual conversational utterance."""
    turn_id: str
    direction: str  # "A->B" or "B->A"
    source_lang: str
    target_lang: str
    speech_start_time: float = 0.0
    speech_end_time: float = 0.0
    stt_start_time: float = 0.0
    stt_end_time: float = 0.0
    mt_start_time: float = 0.0
    mt_end_time: float = 0.0
    tts_start_time: float = 0.0
    tts_first_audio_time: float = 0.0
    tts_end_time: float = 0.0
    pacer_enqueue_time: float = 0.0

    @property
    def speech_to_stt_ms(self) -> float:
        if self.stt_end_time and self.speech_end_time:
            return max(0.0, (self.stt_end_time - self.speech_end_time) * 1000)
        return 0.0

    @property
    def stt_to_mt_ms(self) -> float:
        if self.mt_end_time and self.mt_start_time:
            return max(0.0, (self.mt_end_time - self.mt_start_time) * 1000)
        return 0.0

    @property
    def mt_to_tts_first_byte_ms(self) -> float:
        if self.tts_first_audio_time and self.tts_start_time:
            return max(0.0, (self.tts_first_audio_time - self.tts_start_time) * 1000)
        return 0.0

    @property
    def total_e2e_latency_ms(self) -> float:
        ref_start = self.speech_end_time or self.stt_start_time
        ref_end = self.tts_first_audio_time or self.tts_end_time
        if ref_start and ref_end:
            return max(0.0, (ref_end - ref_start) * 1000)
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "direction": self.direction,
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
            "speech_to_stt_ms": round(self.speech_to_stt_ms, 1),
            "stt_to_mt_ms": round(self.stt_to_mt_ms, 1),
            "mt_to_tts_ms": round(self.mt_to_tts_first_byte_ms, 1),
            "total_e2e_latency_ms": round(self.total_e2e_latency_ms, 1),
        }


@dataclass
class LegState:
    """State machine and audio buffers for one leg of a call."""
    name: str  # "caller" or "receiver"
    language: str
    in_speech: bool = False
    speech_started_at: float = 0.0
    audio_buffer: bytearray = field(default_factory=bytearray)
    chunker: SentenceChunker = field(default_factory=SentenceChunker)
    last_partial_text: str = ""
    last_partial_time: float = 0.0
    turn_counter: int = 0
    is_playing_tts: bool = False


class BidirectionalTranslationBridge:
    """Manages full-duplex simultaneous speech translation between two participants."""

    def __init__(
        self,
        call_id: uuid.UUID,
        caller_language: str = "hi",
        receiver_language: str = "ja",
        mode: str = "human_to_human",
        unified_prompt: str = "",
        on_event: Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
        on_audio_out: Callable[[str, bytes], Coroutine[Any, Any, None]] | None = None,
        on_barge_in: Callable[[str], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        self.call_id = call_id
        self.caller_lang = caller_language
        self.receiver_lang = receiver_language
        self.mode = mode
        self.unified_prompt = unified_prompt
        self.on_event = on_event
        self.on_audio_out = on_audio_out
        self.on_barge_in = on_barge_in

        # Audio Queues (16kHz PCM16 linear audio)
        self.caller_in_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=300)
        self.receiver_in_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=300)

        # Worker Tasks
        self.worker_a_to_b: asyncio.Task | None = None
        self.worker_b_to_a: asyncio.Task | None = None
        self.is_running: bool = False

        # VAD instances (16kHz PCM16)
        self.vad_caller = create_vad("webrtc_energy", sample_rate=16000)
        self.vad_receiver = create_vad("webrtc_energy", sample_rate=16000)

        # Leg States
        self.caller_state = LegState(name="caller", language=caller_language)
        self.receiver_state = LegState(name="receiver", language=receiver_language)

        # Non-blocking degradation tracker
        self.translation_degraded: bool = False

    async def start(self) -> None:
        """Spawn the concurrent dual workers."""
        if self.is_running:
            return
        self.is_running = True
        log.info(
            "Starting BidirectionalTranslationBridge for call %s: %s (%s) <-> %s (%s) [mode=%s]",
            self.call_id, self.caller_state.name, self.caller_lang,
            self.receiver_state.name, self.receiver_lang, self.mode
        )

        self.worker_a_to_b = asyncio.create_task(
            self._leg_worker(
                src_state=self.caller_state,
                dst_state=self.receiver_state,
                in_queue=self.caller_in_queue,
                vad=self.vad_caller,
                direction_label="A->B",
            ),
            name=f"bridge-A2B-{self.call_id}"
        )

        self.worker_b_to_a = asyncio.create_task(
            self._leg_worker(
                src_state=self.receiver_state,
                dst_state=self.caller_state,
                in_queue=self.receiver_in_queue,
                vad=self.vad_receiver,
                direction_label="B->A",
            ),
            name=f"bridge-B2A-{self.call_id}"
        )

    async def stop(self) -> None:
        """Safely terminate all worker loops."""
        self.is_running = False
        if self.worker_a_to_b:
            self.worker_a_to_b.cancel()
        if self.worker_b_to_a:
            self.worker_b_to_a.cancel()
        log.info("BidirectionalTranslationBridge stopped for call %s", self.call_id)

    # ----------------------------------------------------------------------- #
    # Audio Ingestion
    # ----------------------------------------------------------------------- #

    async def feed_caller_pcm16(self, pcm16_chunk: bytes) -> None:
        """Feed 16kHz PCM16 chunk from caller (handset or web client)."""
        if not self.is_running:
            return
        try:
            self.caller_in_queue.put_nowait(pcm16_chunk)
        except asyncio.QueueFull:
            try:
                self.caller_in_queue.get_nowait()
                self.caller_in_queue.put_nowait(pcm16_chunk)
            except Exception:
                pass

    async def feed_receiver_pcm16(self, pcm16_chunk: bytes) -> None:
        """Feed 16kHz PCM16 chunk from receiver (PSTN handset or callee)."""
        if not self.is_running:
            return
        try:
            self.receiver_in_queue.put_nowait(pcm16_chunk)
        except asyncio.QueueFull:
            try:
                self.receiver_in_queue.get_nowait()
                self.receiver_in_queue.put_nowait(pcm16_chunk)
            except Exception:
                pass

    # ----------------------------------------------------------------------- #
    # Worker Loop for a Single Direction
    # ----------------------------------------------------------------------- #

    async def _leg_worker(
        self,
        src_state: LegState,
        dst_state: LegState,
        in_queue: asyncio.Queue[bytes],
        vad: Any,
        direction_label: str,
    ) -> None:
        """Independent asynchronous worker loop for one direction of the call."""
        log.info("Spawned directional translation worker %s for call %s", direction_label, self.call_id)
        try:
            while self.is_running:
                try:
                    chunk = await asyncio.wait_for(in_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    # Silence timeout: check if in-speech buffer has trailing speech to flush
                    if src_state.in_speech and len(src_state.audio_buffer) > 16000 * 2 * 0.4:
                        await self._process_speech_turn(src_state, dst_state, direction_label, force=True)
                    continue

                if not chunk:
                    continue

                # Run VAD on chunk
                vad_events = vad.process(chunk)
                for ev in vad_events:
                    if ev.state == VadState.SPEECH:
                        if not src_state.in_speech:
                            src_state.in_speech = True
                            src_state.speech_started_at = time.perf_counter()
                            src_state.audio_buffer = bytearray(chunk)
                            src_state.chunker.reset()

                            # Barge-in: Speaker just interrupted!
                            if dst_state.is_playing_tts:
                                log.info("Barge-in detected in %s: interrupting playback!", src_state.name)
                                dst_state.is_playing_tts = False
                                if self.on_barge_in:
                                    await self.on_barge_in(dst_state.name)

                            await self._emit_event("call.speech_started", {
                                "speaker": src_state.name,
                                "timestamp": time.time(),
                            })
                    else:  # SILENCE / SPEECH ENDED
                        if src_state.in_speech:
                            src_state.audio_buffer.extend(chunk)
                            src_state.in_speech = False
                            await self._process_speech_turn(src_state, dst_state, direction_label)

                if src_state.in_speech:
                    src_state.audio_buffer.extend(chunk)
                    # Check streaming partial transcription cadence (every ~1.0s)
                    now = time.perf_counter()
                    if now - src_state.last_partial_time >= 1.0 and len(src_state.audio_buffer) >= 16000 * 2 * 0.8:
                        src_state.last_partial_time = now
                        await self._emit_partial_stt(src_state)

        except asyncio.CancelledError:
            log.debug("Worker %s cancelled for call %s", direction_label, self.call_id)
        except Exception as e:
            log.exception("Worker %s crashed for call %s: %s", direction_label, self.call_id, e)

    # ----------------------------------------------------------------------- #
    # Partial Transcription Cadence
    # ----------------------------------------------------------------------- #

    async def _emit_partial_stt(self, state: LegState) -> None:
        try:
            audio_bytes = bytes(state.audio_buffer)
            lang_hint = None if state.language in ("auto", "") else state.language
            chunk, _decision = await ai.transcribe(audio_bytes, 16000, lang_hint=lang_hint)
            text = (chunk.text or "").strip()
            if text and text != state.last_partial_text:
                state.last_partial_text = text
                await self._emit_event("call.transcript_partial", {
                    "speaker": state.name,
                    "language": chunk.language or state.language,
                    "text": text,
                    "is_final": False,
                })
        except Exception:
            pass

    # ----------------------------------------------------------------------- #
    # Finalize Speech Turn & Execute MT -> TTS
    # ----------------------------------------------------------------------- #

    async def _process_speech_turn(
        self,
        src_state: LegState,
        dst_state: LegState,
        direction_label: str,
        force: bool = False,
    ) -> None:
        audio_data = bytes(src_state.audio_buffer)
        src_state.audio_buffer = bytearray()
        src_state.last_partial_text = ""

        if len(audio_data) < 1600:  # <50ms noise blip
            return

        speech_stop_time = time.perf_counter()
        src_state.turn_counter += 1
        turn_id = f"{src_state.name}-{src_state.turn_counter}-{uuid.uuid4().hex[:6]}"

        timing = StageTiming(
            turn_id=turn_id,
            direction=direction_label,
            source_lang=src_state.language,
            target_lang=dst_state.language,
            speech_start_time=src_state.speech_started_at,
            speech_end_time=speech_stop_time,
            stt_start_time=time.perf_counter(),
        )

        # 1. Speech-to-Text
        try:
            lang_hint = None if src_state.language in ("auto", "") else src_state.language
            chunk, decision = await ai.transcribe(audio_data, 16000, lang_hint=lang_hint)
            timing.stt_end_time = time.perf_counter()
            recognized_text = (chunk.text or "").strip()
        except AppError as e:
            await self._handle_error("stt_error", f"Speech recognition failed: {e.message}")
            return
        except Exception as e:
            await self._handle_error("stt_error", f"Speech recognition failed: {e}")
            return

        if not recognized_text:
            return

        # Auto-detect language if needed
        detected_lang = chunk.language or src_state.language
        if detected_lang in ("auto", ""):
            det = await ai.detect_language(recognized_text)
            detected_lang = det.language

        timing.source_lang = detected_lang

        await self._emit_event("call.transcript_final", {
            "turn_id": turn_id,
            "speaker": src_state.name,
            "language": detected_lang,
            "text": recognized_text,
            "confidence": chunk.confidence or 0.95,
            "latency_ms": round(timing.speech_to_stt_ms, 1),
        })

        # 2. Check for AI Voice Agent Mode
        if self.mode == "ai_agent" and src_state.name == "caller":
            await self._handle_ai_agent_turn(
                turn_id=turn_id,
                caller_text=recognized_text,
                caller_lang=detected_lang,
                dst_state=dst_state,
                timing=timing,
            )
            return

        # 3. Machine Translation (Direction A -> B or B -> A)
        timing.mt_start_time = time.perf_counter()
        target_lang = dst_state.language

        # Break text into sentence/phrase chunks using SentenceChunker
        sentence_chunks = src_state.chunker.append(recognized_text)
        flushed = src_state.chunker.flush()
        if flushed:
            sentence_chunks.extend(flushed)

        if not sentence_chunks:
            sentence_chunks = [recognized_text]

        for sentence in sentence_chunks:
            await self._translate_and_synthesize_sentence(
                turn_id=turn_id,
                sentence=sentence,
                source_lang=detected_lang,
                target_lang=target_lang,
                src_state=src_state,
                dst_state=dst_state,
                timing=timing,
            )

    async def _translate_and_synthesize_sentence(
        self,
        turn_id: str,
        sentence: str,
        source_lang: str,
        target_lang: str,
        src_state: LegState,
        dst_state: LegState,
        timing: StageTiming,
    ) -> None:
        """Translate a single sentence chunk and stream its audio to the destination leg."""
        # 1. Translate
        try:
            req = TranslationRequest(
                source_lang=source_lang,
                target_lang=target_lang,
                source_text=sentence,
                domain="conversational",
                intent=Intent.LATENCY_OPTIMIZED,
            )
            res, _decision = await ai.translate(req)
            timing.mt_end_time = time.perf_counter()
            translated_text = res.text if hasattr(res, "text") else getattr(res, "translated_text", str(res))
        except Exception as e:
            await self._handle_error(
                "translation_error",
                f"Translation from {source_lang} to {target_lang} delayed: {e}"
            )
            return

        await self._emit_event("call.translation_final", {
            "turn_id": turn_id,
            "speaker": src_state.name,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "source_text": sentence,
            "translated_text": translated_text,
            "latency_ms": round(timing.stt_to_mt_ms, 1),
        })

        # 2. Text-to-Speech Streaming
        timing.tts_start_time = time.perf_counter()
        dst_state.is_playing_tts = True
        first_audio = True

        try:
            stream, _tts_decision = await ai.synthesize_stream(translated_text, target_lang)
            async for audio_chunk in stream:
                if not dst_state.is_playing_tts:
                    # Speech was barged in while synthesizing!
                    log.debug("Aborting TTS synthesis mid-stream due to barge-in")
                    break

                if first_audio:
                    timing.tts_first_audio_time = time.perf_counter()
                    first_audio = False

                pcm_data = audio_chunk.data
                sample_rate = audio_chunk.sample_rate or 16000

                # Send audio directly to destination leg
                if self.on_audio_out:
                    await self.on_audio_out(dst_state.name, pcm_data)

            timing.tts_end_time = time.perf_counter()

        except Exception as e:
            await self._handle_error("tts_error", f"TTS synthesis failed: {e}")
        finally:
            dst_state.is_playing_tts = False

        # 3. Emit Latency Waterfall Report
        await self._emit_event("call.latency_report", timing.to_dict())

    # ----------------------------------------------------------------------- #
    # AI Voice Agent Mode Handler
    # ----------------------------------------------------------------------- #

    async def _handle_ai_agent_turn(
        self,
        turn_id: str,
        caller_text: str,
        caller_lang: str,
        dst_state: LegState,
        timing: StageTiming,
    ) -> None:
        """Autonomous AI Voice Agent responses with prompt merge instructions."""
        from app.agents.prompt_composer import PromptComposerEngine

        timing.mt_start_time = time.perf_counter()

        # Generate intelligent response using the composed unified prompt
        agent_reply = PromptComposerEngine.test_agent_turn(
            merged_prompt=self.unified_prompt,
            user_message=caller_text,
            user_language=caller_lang,
        )
        timing.mt_end_time = time.perf_counter()

        await self._emit_event("call.translation_final", {
            "turn_id": turn_id,
            "speaker": "ai_agent",
            "source_lang": caller_lang,
            "target_lang": caller_lang,
            "source_text": caller_text,
            "translated_text": agent_reply,
            "latency_ms": round(timing.stt_to_mt_ms, 1),
        })

        # Synthesize agent response back to caller
        timing.tts_start_time = time.perf_counter()
        self.caller_state.is_playing_tts = True
        first_audio = True

        try:
            stream, _decision = await ai.synthesize_stream(agent_reply, caller_lang)
            async for audio_chunk in stream:
                if not self.caller_state.is_playing_tts:
                    break
                if first_audio:
                    timing.tts_first_audio_time = time.perf_counter()
                    first_audio = False

                if self.on_audio_out:
                    await self.on_audio_out("caller", audio_chunk.data)

            timing.tts_end_time = time.perf_counter()
        except Exception as e:
            await self._handle_error("tts_error", f"Voice agent synthesis error: {e}")
        finally:
            self.caller_state.is_playing_tts = False

        await self._emit_event("call.latency_report", timing.to_dict())

    # ----------------------------------------------------------------------- #
    # Resilience & Event Dispatches
    # ----------------------------------------------------------------------- #

    async def _handle_error(self, code: str, msg: str) -> None:
        """Non-blocking translation failure recovery (Requirement #13)."""
        log.warning("Bridge non-blocking error [%s]: %s", code, msg)
        self.translation_degraded = True
        await self._emit_event("call.translation_degraded", {
            "code": code,
            "message": "Live translation is temporarily unavailable. Retrying...",
            "recoverable": True,
            "call_unaffected": True,
        })

    async def _emit_event(self, event_type: str, data: dict[str, Any]) -> None:
        if self.on_event:
            try:
                await self.on_event(event_type, data)
            except Exception as e:
                log.debug("Event emission error (%s): %s", event_type, e)
