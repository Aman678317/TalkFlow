"""Per-speaker realtime audio pipeline (sections 9/10/98/106/107).

mic PCM → [noise gate/VAD] → speech segmentation → streaming STT (partials + final)
→ language ID → CANONICAL SOURCE SEGMENT (persisted, immutable)
→ translation fan-out (dedup per target language) → per-language TTS
→ listener router (per-participant audio_mode / caption_mode).

Design rules enforced here:
- The speaker's source segment is the only semantic source; derivatives carry source_segment_id.
- Processing starts before the utterance ends (partials, incremental fan-out).
- Stale partials are dropped via utterance generation counters.
- Backpressure: bounded concurrent fan-out tasks; overflow degrades (captions-only) and emits
  quality.degraded — the meeting itself never breaks.
- Latency breakdown measured per stage: capture, stt_first_partial, stt_final, translation,
  tts_first_audio, delivery, total_e2e.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from ai.bootstrap import get_router
from ai.interfaces import ProviderUnavailable
from ai.model_router.router import RouteRequest
from ai.providers.vad import get_vad
from globaltalk.core.config import settings
from globaltalk.core.db import session_scope
from globaltalk.core.logging import get_logger
from globaltalk.core.metrics import metrics
from globaltalk.core.storage import get_storage
from globaltalk.models import TranslationSegment, TranscriptSegment
from globaltalk.realtime.hub import (MeetingSession, ParticipantConn, audio_b64,
                                     spawn)
from globaltalk.realtime.protocol import BinaryFrame, EventType

log = get_logger("audio")

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="gt-inference")

CHUNK_SAMPLES = 1600          # 100 ms @ 16 kHz
VAD_START_PROB = 0.18
VAD_END_PROB = 0.10
HANGOVER_MS = 700
MIN_UTTERANCE_MS = 350
MAX_UTTERANCE_MS = 30_000

LATENCY_MODE_PARAMS = {
    "ultra_low_latency": {"partial_interval_ms": 800, "beam": 1},
    "balanced": {"partial_interval_ms": 1500, "beam": 1},
    "high_accuracy": {"partial_interval_ms": 2500, "beam": 4},
}


@dataclass
class Utterance:
    uid: str
    short_id: str
    started_mono_ms: int
    chunks: list[bytes] = field(default_factory=list)
    generations: int = 0
    finalized: bool = False
    t_first_chunk: float = 0.0
    t_first_partial: float | None = None
    t_stt_final: float | None = None

    @property
    def pcm(self) -> bytes:
        return b"".join(self.chunks)

    @property
    def duration_ms(self) -> int:
        return len(self.pcm) // 32  # 16 bytes/ms @16kHz int16 mono


class AudioPipeline:
    def __init__(self, session: MeetingSession, conn: ParticipantConn):
        self.session = session
        self.conn = conn
        self.vad = get_vad(settings.vad_provider)
        self.loop = asyncio.get_event_loop()
        self._pending = bytearray()
        self._in_speech = False
        self._silence_ms = 0
        self._speech_ms = 0
        self._utt: Utterance | None = None
        self._partial_task: asyncio.Task | None = None
        self._partial_inflight = False
        self._last_partial_ms = 0
        self._fanout_sem = asyncio.Semaphore(2)  # backpressure per speaker
        self._shutdown = False
        self._mono_ms = 0
        self.audio_seconds_fed = 0.0

    # ------------------------------------------------------------------ ingest

    async def feed(self, pcm: bytes) -> None:
        """Called for every binary WS frame from this participant's microphone."""
        if self._shutdown or not pcm:
            return
        self.audio_seconds_fed += len(pcm) / 32000.0
        self._pending.extend(pcm)
        while len(self._pending) >= CHUNK_SAMPLES * 2:
            chunk = bytes(self._pending[:CHUNK_SAMPLES * 2])
            del self._pending[:CHUNK_SAMPLES * 2]
            await self._process_chunk(chunk)

    async def _process_chunk(self, chunk: bytes) -> None:
        self._mono_ms += 100
        try:
            prob = self.vad.process_chunk(chunk, settings.audio_sample_rate)
        except Exception:
            prob = 0.5  # VAD failure must not stop the meeting: treat as speech-ish
        if not self._in_speech:
            if prob >= VAD_START_PROB:
                await self._start_utterance(chunk)
            return
        # in speech
        self._utt.chunks.append(chunk)  # type: ignore[union-attr]
        await self._relay_original(chunk)
        if prob < VAD_END_PROB:
            self._silence_ms += 100
        else:
            self._silence_ms = 0
        self._speech_ms += 100
        should_end = (self._silence_ms >= HANGOVER_MS
                      or self._utt.duration_ms >= MAX_UTTERANCE_MS)  # type: ignore[union-attr]
        if should_end and self._utt.duration_ms >= MIN_UTTERANCE_MS:  # type: ignore[union-attr]
            await self._end_utterance()
        elif should_end:
            # too short: drop as noise, keep listening seamlessly
            self._in_speech = False
            self._utt = None
            self._silence_ms = 0
            return
        # incremental partials while speaking
        params = LATENCY_MODE_PARAMS.get(self.conn.latency_mode,
                                         LATENCY_MODE_PARAMS["balanced"])
        if (not self._partial_inflight
                and self._utt.duration_ms - self._last_partial_ms >=  # type: ignore[union-attr]
                params["partial_interval_ms"]):
            self._schedule_partial(params)

    async def _start_utterance(self, first_chunk: bytes) -> None:
        uid = uuid.uuid4().hex
        self._utt = Utterance(uid=uid, short_id=uid[:16], started_mono_ms=self._mono_ms,
                              t_first_chunk=time.perf_counter())
        self._utt.chunks.append(first_chunk)
        self._in_speech = True
        self._silence_ms = 0
        self._speech_ms = 0
        self._last_partial_ms = 0
        evt = self.session.record(EventType.SPEECH_STARTED, speaker_id=self.conn.participant_id,
                                  utterance_id=uid, mono_ms=self._mono_ms)
        await self.session.broadcast(evt, exclude=None)

    def _schedule_partial(self, params: dict) -> None:
        assert self._utt is not None
        utt, gen = self._utt, self._utt.generations
        pcm = utt.pcm
        self._partial_inflight = True
        self._last_partial_ms = utt.duration_ms

        async def run():
            try:
                result = await self.loop.run_in_executor(
                    _executor, self._stt, pcm, self.conn.speaking_language, params["beam"])
                if (self._shutdown or self._utt is not utt or utt.generations != gen
                        or utt.finalized or not result.text):
                    return  # stale partial → drop (cancellation semantics)
                if utt.t_first_partial is None:
                    utt.t_first_partial = time.perf_counter()
                evt = self.session.record(
                    EventType.TRANSCRIPT_PARTIAL, speaker_id=self.conn.participant_id,
                    utterance_id=utt.uid, language=result.language, text=result.text,
                    is_final=False, confidence=round(result.confidence, 3))
                await self._deliver_captions(evt, result.language, original_text=result.text)
            except ProviderUnavailable as exc:
                await self._emit_degraded("stt_unavailable", str(exc))
            except Exception:
                log.exception("partial_stt_failed")
            finally:
                self._partial_inflight = False

        self._partial_task = asyncio.create_task(run())

    def _stt(self, pcm: bytes, speaking_language: str, beam: int):
        router = get_router()
        lang = None if speaking_language.upper() == "AUTO" else speaking_language.split("-")[0]

        def call(p):
            if hasattr(p, "model_size"):  # faster-whisper: use configured beam
                import ai.providers.stt.faster_whisper as fw
                fw.load_model(p.model_size, p.device, p.compute_type)
                import numpy as np
                audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
                kwargs = {"beam_size": beam, "vad_filter": False,
                          "condition_on_previous_text": False}
                if lang:
                    kwargs["language"] = fw._lang_map(lang)
                started = time.perf_counter()
                segs, info = fw._model.transcribe(audio, **kwargs)
                text = "".join(s.text for s in segs).strip()
                from ai.interfaces import STTResult
                return STTResult(text=text, language=fw._lang_map(info.language or lang or ""),
                                 language_probability=float(info.language_probability or 0),
                                 confidence=float(info.language_probability or 0),
                                 provider=p.name, model=f"whisper-{p.model_size}",
                                 duration_ms=(time.perf_counter() - started) * 1000)
            return p.transcribe(pcm, settings.audio_sample_rate, language=lang)

        result, route = router.execute(RouteRequest(task="stt", source_language=lang or ""),
                                       call)
        metrics.observe_stt(route.provider_name, result.language, result.duration_ms)
        return result

    # ------------------------------------------------------------------ finalize

    async def _end_utterance(self) -> None:
        utt = self._utt
        assert utt is not None
        utt.finalized = True
        utt.generations += 1
        self._in_speech = False
        self._utt = None
        pcm = utt.pcm
        duration_ms = utt.duration_ms
        t_end = time.perf_counter()

        ended_evt = self.session.record(EventType.SPEECH_ENDED,
                                        speaker_id=self.conn.participant_id,
                                        utterance_id=utt.uid, duration_ms=duration_ms)
        await self.session.broadcast(ended_evt)

        speaking_language = self.conn.speaking_language
        conn = self.conn
        session = self.session

        async def finalize():
            try:
                result = await self.loop.run_in_executor(
                    _executor, self._stt, pcm, speaking_language,
                    LATENCY_MODE_PARAMS.get(conn.latency_mode, {}).get("beam", 1))
            except ProviderUnavailable as exc:
                await self._emit_degraded("stt_unavailable", str(exc))
                return
            except Exception:
                log.exception("final_stt_failed")
                await self._emit_degraded("stt_error", "final transcription failed")
                return
            if not result.text:
                return  # silence/noise burst; no canonical segment created
            utt.t_stt_final = time.perf_counter()
            stt_ms = (utt.t_stt_final - t_end) * 1000

            # ---- persist CANONICAL SOURCE (immutable human source of truth)
            latency = {
                "capture_ms": round((utt.t_first_partial or utt.t_stt_final) - utt.t_first_chunk, 1)
                if utt.t_first_partial else None,
                "stt_first_partial_ms": round((utt.t_first_partial - utt.t_first_chunk) * 1000, 1)
                if utt.t_first_partial else None,
                "stt_final_ms": round(stt_ms + duration_ms, 1),
                "stt_compute_ms": round(stt_ms, 1),
            }
            segment_id, seq = await self.loop.run_in_executor(
                _executor, self._persist_segment, utt, result, latency, duration_ms)

            # archive original audio (retention-controlled), keyed to the canonical segment
            if duration_ms >= 500:
                spawn(self._archive_audio(utt, segment_id),
                      name=f"archive-{utt.uid[:8]}")

            final_evt = session.record(
                EventType.TRANSCRIPT_FINAL, speaker_id=conn.participant_id,
                utterance_id=utt.uid, segment_id=segment_id, sequence_hint=seq,
                language=result.language, text=result.text, is_final=True,
                confidence=round(result.confidence, 3), stt_provider=result.provider,
                stt_model=result.model, latency=latency,
                display_name=conn.display_name)
            await self._deliver_captions(final_evt, result.language, result.text,
                                         final=True)

            # ---- translation fan-out (async, deduplicated per (segment, target lang))
            try:
                async with self._fanout_sem:
                    await self._fanout(segment_id, result.language, result.text,
                                       utt, t_end)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("fanout_failed", extra={"segment_id": segment_id})
                await self._emit_degraded("translation_pipeline_error",
                                          "translation fan-out failed")

        spawn(finalize(), name=f"finalize-{utt.uid[:8]}")

    def _persist_segment(self, utt: Utterance, result, latency: dict,
                         duration_ms: int) -> tuple[str, int]:
        with session_scope() as db:
            from globaltalk.services.meetings import next_segment_sequence
            seq = next_segment_sequence(db, self.session.meeting_id)
            row = TranscriptSegment(
                org_id=self.session.org_id, meeting_id=self.session.meeting_id,
                participant_id=self.conn.participant_id, sequence=seq,
                language=result.language, text=result.text, is_final=True,
                confidence=round(result.confidence, 4), stt_provider=result.provider,
                stt_model=result.model, started_at_ms=utt.started_mono_ms,
                ended_at_ms=utt.started_mono_ms + duration_ms, latency=latency)
            db.add(row)
            db.flush()
            sid = row.id
            db.commit()
            return sid, seq

    async def _archive_audio(self, utt: Utterance, segment_id: str) -> None:
        try:
            from ai.providers.stt.faster_whisper import pcm16_to_wav_bytes
            wav = pcm16_to_wav_bytes(utt.pcm, settings.audio_sample_rate)
            key = f"meetings/{self.session.meeting_id}/audio/{utt.uid}.wav"
            await self.loop.run_in_executor(_executor, get_storage().put, key, wav,
                                            "audio/wav")

            def _set_key():
                with session_scope() as db:
                    db.query(TranscriptSegment).filter(
                        TranscriptSegment.id == segment_id).update(
                        {"audio_key": key})

            await self.loop.run_in_executor(_executor, _set_key)
        except Exception:
            log.exception("audio_archive_failed", extra={"utterance": utt.uid})

    # ------------------------------------------------------------------ fan-out

    async def _fanout(self, segment_id: str, source_language: str, source_text: str,
                      utt: Utterance, t_speech_end: float) -> None:
        session, conn = self.session, self.conn
        targets = session.required_target_languages(source_language, exclude=conn.participant_id)
        if not targets:
            return
        started_evt = session.record(EventType.TRANSLATION_STARTED,
                                     speaker_id=conn.participant_id,
                                     segment_id=segment_id,
                                     source_language=source_language,
                                     target_languages=sorted(targets))
        await session.broadcast(started_evt, exclude=conn.participant_id)

        tasks = [self._translate_for_language(segment_id, source_language, target,
                                              source_text, utt, t_speech_end)
                 for target in sorted(targets)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for target, res in zip(sorted(targets), results):
            if isinstance(res, Exception):
                log.error("fanout_target_failed",
                          extra={"target": target, "segment_id": segment_id,
                                 "error": f"{type(res).__name__}: {res}"})
                await self._emit_translation_failed(segment_id, target, str(res)[:200])

    async def _translate_for_language(self, segment_id: str, source_language: str,
                                      target_language: str, source_text: str,
                                      utt: Utterance, t_speech_end: float) -> None:
        session, conn = self.session, self.conn
        cache_key = session.translation_cache_key(segment_id, target_language)
        cached = session.translation_cache.get(cache_key)
        t0 = time.perf_counter()

        if cached is None:
            # DEDUP: generate each (segment, target language) exactly once (section 88)
            log.info("fanout_target_start", extra={"target": target_language,
                                                   "segment_id": segment_id})
            try:
                result = await self.loop.run_in_executor(
                    _executor, self._translate_sync, source_text, source_language,
                    target_language)
            except ProviderUnavailable as exc:
                log.warning("fanout_target_unavailable",
                            extra={"target": target_language, "reason": str(exc)[:200]})
                await self._emit_translation_failed(segment_id, target_language, str(exc))
                return
            log.info("fanout_target_translated",
                     extra={"target": target_language, "provider": result.provider,
                            "flags": result.quality_flags,
                            "ms": round((time.perf_counter() - t0) * 1000)})
            t_translate = time.perf_counter()
            entry = {
                "text": result.text, "provider": result.provider, "model": result.model,
                "quality_flags": result.quality_flags, "latency_ms": (t_translate - t0) * 1000,
                "untranslated": "untranslated_fallback" in result.quality_flags,
                "translation_segment_id": None, "audio": None,
            }
            if not entry["untranslated"]:
                entry["translation_segment_id"] = await self.loop.run_in_executor(
                    _executor, self._persist_translation, segment_id, source_language,
                    target_language, result)
                metrics.observe_translation(result.provider, f"{source_language}-{target_language}",
                                            entry["latency_ms"])
            session.translation_cache[cache_key] = entry
            cached = entry
        else:
            t_translate = time.perf_counter()

        # ---- deliver translated captions to listeners of this language
        listeners = session.listeners_for_language(target_language, exclude=conn.participant_id)
        caption_listeners = [p for p in listeners if p.caption_mode in ("translated", "both")]
        if caption_listeners and cached["translation_segment_id"]:
            evt = session.record(
                EventType.TRANSLATION_FINAL, speaker_id=conn.participant_id,
                segment_id=segment_id, source_segment_id=segment_id,
                translation_id=cached["translation_segment_id"],
                source_language=source_language, target_language=target_language,
                text=cached["text"], provider=cached["provider"], model=cached["model"],
                quality_flags=cached["quality_flags"],
                latency_ms=round(cached["latency_ms"], 1),
                display_name=conn.display_name)
            await asyncio.gather(*(session.send(p, evt) for p in caption_listeners),
                                 return_exceptions=True)
        elif cached["untranslated"]:
            evt = session.record(
                EventType.TRANSLATION_FAILED, speaker_id=conn.participant_id,
                segment_id=segment_id, target_language=target_language,
                reason="translation_unavailable", recoverable=True,
                user_message=("Live translation is temporarily unavailable. "
                              "Original captions remain available."))
            await asyncio.gather(*(session.send(p, evt) for p in caption_listeners),
                                 return_exceptions=True)

        # ---- TTS once per language, then fan out audio to listeners that want it
        audio_listeners = [p for p in listeners if p.audio_mode in ("translated", "mixed")]
        if not audio_listeners or cached["untranslated"]:
            return
        if cached["audio"] is None:
            try:
                wav = await self.loop.run_in_executor(
                    _executor, self._tts_sync, cached["text"], target_language)
            except ProviderUnavailable as exc:
                # captions-only fallback (section 89): explicit, never silent
                evt = session.record(
                    EventType.QUALITY_DEGRADED, speaker_id=conn.participant_id,
                    segment_id=segment_id, target_language=target_language,
                    reason="tts_unavailable", recoverable=True,
                    user_message=("Translated voice is unavailable for this language. "
                                  "Translated captions remain active."))
                await asyncio.gather(*(session.send(p, evt) for p in audio_listeners),
                                     return_exceptions=True)
                cached["audio"] = False
                return
            t_tts = time.perf_counter()
            cached["audio"] = wav
            cached["tts_ms"] = (t_tts - t_translate) * 1000
            if cached.get("translation_segment_id"):
                spawn(self._store_tts_audio(cached["translation_segment_id"],
                                            segment_id, target_language, wav),
                      name=f"tts-store-{segment_id[:8]}")

        if cached["audio"] is False:
            return
        wav = cached["audio"]
        t_delivery = time.perf_counter()
        total_e2e_ms = (t_delivery - utt.t_first_chunk) * 1000
        latency = {
            "stt_first_partial_ms": round((utt.t_first_partial - utt.t_first_chunk) * 1000, 1)
            if utt.t_first_partial else None,
            "stt_final_ms": round((utt.t_stt_final - utt.t_first_chunk) * 1000, 1)
            if utt.t_stt_final else None,
            "translation_ms": round(cached["latency_ms"], 1),
            "tts_first_audio_ms": round(cached.get("tts_ms", 0), 1),
            "delivery_ms": round((t_delivery - t_translate) * 1000, 1),
            "total_e2e_latency_ms": round(total_e2e_ms, 1),
        }
        metrics.observe_e2e(f"{source_language}-{target_language}", total_e2e_ms)
        metrics.observe("realtime_translation_latency_ms", cached["latency_ms"],
                        {"pair": f"{source_language}-{target_language}"})

        tts_evt = session.record(
            EventType.TTS_COMPLETED, speaker_id=conn.participant_id,
            segment_id=segment_id, source_segment_id=segment_id,
            target_language=target_language, audio_format="wav",
            audio=audio_b64(wav), synthetic=True, latency=latency,
            utterance_id=utt.uid)
        await asyncio.gather(*(session.send(p, tts_evt) for p in audio_listeners),
                             return_exceptions=True)
        lat_evt = session.record(EventType.QUALITY_LATENCY, speaker_id=conn.participant_id,
                                 segment_id=segment_id, target_language=target_language,
                                 **latency)
        await asyncio.gather(*(session.send(p, lat_evt) for p in audio_listeners),
                             return_exceptions=True)

    def _translate_sync(self, text: str, source_language: str, target_language: str):
        router = get_router()
        result, route = router.execute(
            RouteRequest(task="mt", source_language=source_language,
                         target_language=target_language, intent="latency_optimized"),
            lambda p: p.translate(text, source_language, target_language))
        return result

    def _tts_sync(self, text: str, language: str) -> bytes:
        router = get_router()
        result, route = router.execute(
            RouteRequest(task="tts", target_language=language),
            lambda p: p.synthesize(text, language))
        metrics.observe_tts(route.provider_name, language, result.latency_ms)
        return result.audio

    def _persist_translation(self, segment_id: str, source_language: str,
                             target_language: str, result) -> str:
        with session_scope() as db:
            row = TranslationSegment(
                org_id=self.session.org_id, meeting_id=self.session.meeting_id,
                source_segment_id=segment_id, source_kind="transcript",
                source_language=source_language, target_language=target_language,
                text=result.text, provider=result.provider, model=result.model,
                confidence=result.confidence, latency_ms=result.latency_ms,
                quality_flags=result.quality_flags)
            db.add(row)
            db.commit()
            return row.id

    async def _store_tts_audio(self, translation_id: str, segment_id: str,
                               target_language: str, wav: bytes) -> None:
        try:
            key = (f"meetings/{self.session.meeting_id}/tts/"
                   f"{segment_id[:8]}_{target_language}.wav")
            await self.loop.run_in_executor(_executor, get_storage().put, key, wav, "audio/wav")

            def _update():
                with session_scope() as db:
                    db.query(TranslationSegment).filter(
                        TranslationSegment.id == translation_id).update(
                        {"tts_audio_key": key, "tts_provider": "kokoro"})
            await self.loop.run_in_executor(_executor, _update)
            evt = self.session.record(EventType.AUDIO_PUBLISHED,
                                      speaker_id=self.conn.participant_id,
                                      segment_id=segment_id, target_language=target_language,
                                      storage="object_store", key=key)
            await self.session.broadcast(evt, only=self.session.listeners_for_language(
                target_language, exclude=self.conn.participant_id))
        except Exception:
            log.warning("tts_store_failed", extra={"segment": segment_id})

    # ------------------------------------------------------------------ delivery

    async def _deliver_captions(self, evt: dict, language: str, text: str,
                                final: bool = False) -> None:
        """Route an original-language caption event per participant caption_mode."""
        session = self.session
        for p in list(session.participants.values()):
            if not p.connected:
                continue
            if p.listening_language == language or p.caption_mode in ("original", "both"):
                await session.send(p, evt)

    async def _relay_original(self, chunk: bytes) -> None:
        """Original voice relay to every listener except the speaker.

        Clients filter by audio_mode + source language: in 'translated' mode a client
        plays the original relay only while the speaker's language equals the listener's
        language (they understand the source natively); otherwise they play TTS audio.
        This keeps 'original audio continues even if AI fails' (§3) structurally true."""
        utt = self._utt
        if utt is None:
            return
        frame = BinaryFrame.encode_original(utt.short_id, chunk)
        targets = [p for p in self.session.participants.values()
                   if p.connected and p.participant_id != self.conn.participant_id]
        await asyncio.gather(*(self.session.send_binary(p, frame) for p in targets),
                             return_exceptions=True)

    async def _emit_degraded(self, reason: str, detail: str) -> None:
        evt = self.session.record(
            EventType.QUALITY_DEGRADED, speaker_id=self.conn.participant_id,
            reason=reason, recoverable=True, details=detail[:300],
            user_message=("Live translation is temporarily unavailable. "
                          "The original conversation continues."))
        await self.session.broadcast(evt)

    async def _emit_translation_failed(self, segment_id: str, target_language: str,
                                       reason: str) -> None:
        evt = self.session.record(
            EventType.TRANSLATION_FAILED, speaker_id=self.conn.participant_id,
            segment_id=segment_id, target_language=target_language, reason=reason,
            recoverable=True,
            user_message="Translation is taking longer than expected. "
                         "The original audio is still active.")
        listeners = self.session.listeners_for_language(target_language,
                                                        exclude=self.conn.participant_id)
        await asyncio.gather(*(self.session.send(p, evt) for p in listeners),
                             return_exceptions=True)

    def shutdown(self) -> None:
        self._shutdown = True
        if self._partial_task and not self._partial_task.done():
            self._partial_task.cancel()
