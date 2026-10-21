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
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from app.realtime.agents.translation import ProviderTranslation
from app.realtime.translation_fanout import (
    CanonicalSegment,
    FanOutRecipient,
    TranslationFanOut,
)
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


#: Primary legs get per-sentence audio streaming (unchanged legacy behavior).
#: Everything else on the bridge is a §306 caption seat — it joins through the
#: :class:`TranslationFanOut` router until a real carrier media channel exists
#: for it, at which point its audio delivery can be wired (documented next).
PRIMARY_LEG_NAMES = ("caller", "receiver")


@dataclass
class BridgeLegSpec:
    """Routing-table entry for a bridge leg (plan §306 seat parity).

    ``caller``/``receiver`` names are reserved for the primary audio legs;
    extra legs are caption-seat participants serviced by the fan-out core.
    """

    name: str
    hear_lang: str = "en"
    mode: str = "translated"

    def __post_init__(self) -> None:
        if self.mode not in ("translated", "original"):
            raise ValueError(
                f"leg mode must be 'translated' or 'original', got {self.mode!r}")
        if not self.name.strip():
            raise ValueError("leg name must be non-empty")


#: LRU bound for the shared translation seam's memoization — an audio bridge
#: is a bounded conversation; once the cache is full the OLDEST distinct
#: request is evicted and its repeat honestly re-asks the provider. Small by
#: design: per-bridge memory, never a cross-call cache.
TRANSLATION_CACHE_MAXSIZE = 64


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
        extra_legs: list[BridgeLegSpec] | None = None,
        caption_sink: Any | None = None,
        tenant_private_only: bool = False,
    ) -> None:
        self.call_id = call_id
        self.caller_lang = caller_language
        self.receiver_lang = receiver_language
        self.mode = mode
        self.unified_prompt = unified_prompt
        self.on_event = on_event
        self.on_audio_out = on_audio_out
        self.on_barge_in = on_barge_in
        self.caption_sink = caption_sink
        # Tenant-private call (issue #109 class 3, finding 8): the bridge used
        # to hard-code a latency intent, so a call could never be routed
        # private-only. The flag rides into the translation request.
        self.tenant_private_only = bool(tenant_private_only)

        # §306 routing table: primary legs are implicit `translated` seats, so
        # the legacy two-leg behavior is byte-identical; extra legs opt into the
        # fan-out router (captions-only until carrier media exists).
        self._legs: dict[str, BridgeLegSpec] = {
            "caller": BridgeLegSpec("caller", caller_language, "translated"),
            "receiver": BridgeLegSpec("receiver", receiver_language, "translated"),
        }
        self.extra_legs: list[BridgeLegSpec] = []
        for spec in (extra_legs or []):
            if spec.name in PRIMARY_LEG_NAMES:
                raise ValueError(
                    f"{spec.name!r} is a primary leg name — use "
                    "caller_language/receiver_language instead")
            if spec.name in self._legs:
                raise ValueError(f"duplicate bridge leg name {spec.name!r}")
            self._legs[spec.name] = spec
            self.extra_legs.append(spec)

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

        # Translation seam (§306 + §B1): the ONE place the bridge may request
        # a provider translation — the fan-out router first, and (same slice)
        # the per-sentence primary audio path through the same method.
        self._fanout = TranslationFanOut(self._bridge_translate)
        # The seam's memo: one provider call per DISTINCT
        # (source_lang, target_lang, text) for this bridge's lifetime,
        # LRU-bounded; a FAILED request is never cached, so the next
        # identical request honestly retries the provider.
        self._translation_cache: OrderedDict[
            tuple[str, str, str], ProviderTranslation] = OrderedDict()
        self._translation_seam_lock = asyncio.Lock()

    # ----------------------------------------------------------------------- #
    # Shared translation seam (fan-out router + per-sentence audio path)
    # ----------------------------------------------------------------------- #

    async def _bridge_translate(
        self, text: str, source_lang: str, target_lang: str, *,
        segment_id: str | None = None, speaker_id: str | None = None,
    ) -> ProviderTranslation:
        """The ONE translation seam of the bridge.

        Both the fan-out router and the per-sentence primary audio path
        request provider translation through this single seam, so the
        whole bridge satisfies one guarantee: exactly one provider call
        per DISTINCT ``(source_lang, target_lang, text)`` — a receiver
        and a caption seat wanting the same translation share one
        provider result verbatim (plan §5/§306 cross-path dedupe).

        The provider is handed the canonical segment text only — never a
        partial and never a translation of a translation (rule §16).
        ``segment_id``/``speaker_id`` ride along for the router's
        contract; they never key and never alter the translation. The
        memo is LRU-bounded (``TRANSLATION_CACHE_MAXSIZE``) and holds
        only this bridge's successful results.
        """
        key = (source_lang, target_lang, text)
        async with self._translation_seam_lock:
            cached = self._translation_cache.get(key)
            if cached is not None:
                self._translation_cache.move_to_end(key)
                return cached
            req = TranslationRequest(
                text=text,
                source_lang=source_lang,
                target_lang=target_lang,
                domain="conversational",
                intent=Intent.PRIVATE_ONLY if self.tenant_private_only
                else Intent.LATENCY_OPTIMIZED,
            )
            # Provider call under the seam lock: concurrent identical
            # requests serialize onto the ONE call instead of racing to
            # emit two.
            res, _decision = await ai.translate(req)
            translated = res.text if hasattr(res, "text") else getattr(
                res, "translated_text", str(res))
            out = ProviderTranslation(
                text=(translated or "").strip(),
                provider=getattr(res, "provider", "unknown") or "unknown",
                model=getattr(res, "model", "unknown") or "unknown",
            )
            self._translation_cache[key] = out
            while len(self._translation_cache) > TRANSLATION_CACHE_MAXSIZE:
                self._translation_cache.popitem(last=False)
            return out

    async def _fan_out_to_extra_legs(
        self, turn_id: str, speaker_leg_name: str,
        speaker_lang: str, recognized_text: str,
    ) -> None:
        """Route one canonical caller turn to every caption-only extra leg.

        Non-blocking: called outside the per-sentence audio path; failures are
        reported per-seat and never touch the primary two-leg flow.
        """
        recipients = [
            FanOutRecipient(seat_id=spec.name, hear_lang=spec.hear_lang,
                            mode=spec.mode)
            for name, spec in self._legs.items()
            if name not in PRIMARY_LEG_NAMES
        ]
        if not recipients:
            return
        segment = CanonicalSegment(
            segment_id=turn_id,
            speaker_seat_id=speaker_leg_name,
            speaker_lang=speaker_lang,
            text=recognized_text,
        )
        result = await self._fanout.run(segment, recipients)

        for delivery in result.deliveries:
            payload = {
                "turn_id": turn_id,
                "seat": delivery.seat_id,
                "lang": delivery.lang,
                "text": delivery.text,
                "origin": delivery.origin,
                "provider": delivery.provider,
                "model": delivery.model,
                # honest boundary: extra legs have no carrier media channel yet
                "audio": False,
            }
            await self._emit_event("call.caption_delivered", payload)
            await self._persist_caption(turn_id, delivery)

        for failure in result.failures:
            for seat_id in failure.seat_ids:
                await self._emit_event("call.caption_unavailable", {
                    "turn_id": turn_id,
                    "seat": seat_id,
                    "target_lang": failure.target_lang,
                    "reason": failure.error,
                    "call_unaffected": True,
                })

    async def _persist_caption(self, turn_id: str, delivery: Any) -> None:
        """Best-effort ``call_events`` row for a routed caption (audit only)."""
        if self.caption_sink is None:
            return
        try:
            await self.caption_sink.record("bridge_caption_delivered", {
                "call_id": str(self.call_id),
                "turn_id": turn_id,
                "seat": delivery.seat_id,
                "lang": delivery.lang,
                "text": delivery.text,
                "origin": delivery.origin,
                "provider": delivery.provider,
                "model": delivery.model,
                "audio": False,
            })
        except Exception as exc:  # noqa: BLE001 — audit is best-effort (plan §7)
            log.debug("caption sink error: %s", exc)

    def set_leg_mode(self, leg_name: str, mode: str) -> None:
        """Mid-call seat mode switch (plan §306: original ↔ translated live).

        The next fan-out turn honors the flip — no dialect re-negotiation, no
        provider change: only the routing decision changes. Unknown legs and
        unknown modes are rejected explicitly (fail closed).
        """
        if leg_name not in self._legs:
            raise KeyError(f"unknown bridge leg {leg_name!r}")
        if mode not in ("translated", "original"):
            raise ValueError(
                f"leg mode must be 'translated' or 'original', got {mode!r}")
        old = self._legs[leg_name]
        self._legs[leg_name] = BridgeLegSpec(
            name=old.name, hear_lang=old.hear_lang, mode=mode)
        if leg_name not in PRIMARY_LEG_NAMES:
            self.extra_legs = [
                spec if spec.name != leg_name else self._legs[leg_name]
                for spec in self.extra_legs
            ]

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

        # §306 parity: route the canonical turn to caption-only extra legs.
        # Never in ai_agent mode (agent replies route separately when wired).
        # Non-blocking: a fan-out failure never breaks the two-leg flow.
        if self.extra_legs and self.mode != "ai_agent":
            try:
                await self._fan_out_to_extra_legs(
                    turn_id, src_state.name, detected_lang, recognized_text)
            except Exception as e:
                await self._handle_error(
                    "fanout_error", f"Extra-leg fan-out delayed: {e}")

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
        # 1. Translate — through the ONE shared seam: the same request shape
        # as the fan-out router, and if a caption seat already fetched this
        # (source, target, text) the receiver rides the cached result.
        try:
            out = await self._bridge_translate(
                sentence, source_lang, target_lang,
                segment_id=turn_id, speaker_id=src_state.name)
            timing.mt_end_time = time.perf_counter()
            translated_text = out.text
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
