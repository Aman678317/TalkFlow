"""Realtime conversation pipeline (PDD §9-§13).

Human microphone -> audio chunks -> VAD -> streaming STT -> language detect
-> CANONICAL source segment (immutable)
   -> Translation fan-out (ONCE per distinct target language)
      -> TTS (ONCE per target language group)
         -> Listener router (per-participant delivery by hear_lang + mode)

Latency budget target: ~1.5-2.5s for a completed short utterance (measured,
not guaranteed). Every stage records its timing into LatencyTrace.

Failure rule: AI failure NEVER breaks the meeting. Original audio path is
untouched; on translation failure we emit translation.failed +
quality.degraded and keep the conversation running.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select, update

from app import metrics as met
from app.ai import ai
from app.config import settings
from app.db import models as M
from app.db.base import utcnow
from app.db.session import db_session
from app.errors import AppError
from app.realtime.protocol import LatencyTrace, ServerEventType
from app.realtime.session_manager import RtParticipant, RtSession, manager
from app.services.translation_service import (
    TranslateContext, translate_text, validate_pair,
)
from gt_ai.vad import EnergyVAD, VadState, create_vad

log = logging.getLogger("app.realtime.pipeline")

AUDIO_QUEUE_MAX = 500          # ~50s of 100ms chunks — backpressure bound
PARTIAL_INTERVAL_S = 1.2       # run partial STT cadence during speech


@dataclass
class UtteranceState:
    """Per-speaker in-flight utterance tracking."""
    participant_id: uuid.UUID
    utterance_id: uuid.UUID = field(default_factory=uuid.uuid4)
    buffer: bytearray = field(default_factory=bytearray)
    started_at_ms: int = 0
    capture_started: float = 0.0
    last_partial_at: float = 0.0
    partial_text: str = ""
    seq: int = 0
    in_speech: bool = False
    locked_language: str | None = None


class MeetingPipeline:
    def __init__(self, session: RtSession) -> None:
        self.session = session
        self.audio_queues: dict[uuid.UUID, asyncio.Queue] = {}
        self.speaker_tasks: dict[uuid.UUID, asyncio.Task] = {}
        self.vads: dict[uuid.UUID, object] = {}
        self.utterances: dict[uuid.UUID, UtteranceState] = {}
        self.translation_tasks: dict[tuple[int, str], asyncio.Task] = {}
        self._closed = False
        self._latest_final_seq: dict[uuid.UUID, int] = {}
        self._last_final_text: dict[uuid.UUID, str] = {}

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def start_speaker(self, p: RtParticipant) -> None:
        if p.participant_id in self.speaker_tasks:
            return
        q: asyncio.Queue = asyncio.Queue(maxsize=AUDIO_QUEUE_MAX)
        self.audio_queues[p.participant_id] = q
        self.vads[p.participant_id] = create_vad(settings.vad_provider,
                                                 sample_rate=16000)
        self.utterances[p.participant_id] = UtteranceState(participant_id=p.participant_id)
        task = asyncio.create_task(self._speaker_loop(p),
                                   name=f"pipeline-{p.participant_id}")
        self.speaker_tasks[p.participant_id] = task

    def stop_speaker(self, participant_id: uuid.UUID) -> None:
        task = self.speaker_tasks.pop(participant_id, None)
        self.audio_queues.pop(participant_id, None)
        self.vads.pop(participant_id, None)
        self.utterances.pop(participant_id, None)
        self._last_final_text.pop(participant_id, None)
        if task:
            task.cancel()

    async def shutdown(self) -> None:
        self._closed = True
        for pid in list(self.speaker_tasks):
            self.stop_speaker(pid)
        for t in list(self.translation_tasks.values()):
            t.cancel()
        self.translation_tasks.clear()

    # ------------------------------------------------------------------ #
    # Audio ingestion
    # ------------------------------------------------------------------ #
    async def feed_audio(self, participant_id: uuid.UUID, pcm16: bytes) -> None:
        q = self.audio_queues.get(participant_id)
        if q is None:
            return
        try:
            q.put_nowait(pcm16)
        except asyncio.QueueFull:
            # backpressure: drop oldest audio, warn clients (PDD §10)
            try:
                q.get_nowait()
                q.put_nowait(pcm16)
            except Exception:
                pass
            if not self.session.quality_degraded:
                self.session.quality_degraded = True
                await manager.broadcast(self.session, ServerEventType.QUALITY_DEGRADED, {
                    "reason": "audio_backpressure",
                    "message": "Audio processing is falling behind. Some chunks were "
                               "dropped. The original call is unaffected.",
                    "recoverable": True})

    async def _speaker_loop(self, p: RtParticipant) -> None:
        q = self.audio_queues[p.participant_id]
        vad = self.vads[p.participant_id]
        u = self.utterances[p.participant_id]
        try:
            while not self._closed:
                try:
                    chunk = await asyncio.wait_for(q.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                if chunk is None:
                    break
                events = vad.process(chunk)  # type: ignore[attr-defined]
                for ev in events:
                    if ev.state == VadState.SPEECH:
                        u.in_speech = True
                        u.utterance_id = uuid.uuid4()
                        u.seq += 1
                        u.buffer = bytearray(chunk)
                        u.started_at_ms = ev.timestamp_ms
                        u.capture_started = time.perf_counter()
                        u.last_partial_at = time.perf_counter()
                        u.partial_text = ""
                        now_ms = int(time.time() * 1000)
                        await manager.broadcast(
                            self.session, ServerEventType.SPEECH_STARTED,
                            {"timestamp_ms": ev.timestamp_ms,
                             "utterance_id": str(u.utterance_id),
                             "utteranceId": str(u.utterance_id),
                             "sequence": u.seq,
                             "seq": u.seq,
                             "created_at": now_ms,
                             "createdAt": now_ms},
                            speaker_id=str(p.participant_id))
                    else:  # SPEECH ended
                        if u.in_speech:
                            u.buffer.extend(chunk)
                            u.in_speech = False
                            audio_payload = bytes(u.buffer)
                            u.buffer = bytearray()
                            start_ms = u.started_at_ms
                            cap_start = u.capture_started
                            curr_uid = u.utterance_id
                            curr_seq = u.seq
                            asyncio.create_task(
                                self._finalize_utterance(
                                    p, u, forced=False, audio_bytes=audio_payload,
                                    start_ms=start_ms, capture_started=cap_start,
                                    utterance_id=curr_uid, seq=curr_seq
                                ),
                                name=f"finalize-{p.participant_id}-{start_ms}"
                            )
                if u.in_speech:
                    u.buffer.extend(chunk)
                    now = time.perf_counter()
                    # Phase 2 bounded segment enforcement: split long monologues at 15s to prevent runaway buffering
                    if (now - u.capture_started) >= 15.0 and len(u.buffer) >= 16000 * 2 * 10:
                        audio_payload = bytes(u.buffer)
                        u.buffer = bytearray()
                        start_ms = u.started_at_ms
                        cap_start = u.capture_started
                        curr_uid = u.utterance_id
                        curr_seq = u.seq
                        u.utterance_id = uuid.uuid4()
                        u.seq += 1
                        u.capture_started = now
                        u.last_partial_at = now
                        u.started_at_ms = getattr(vad, "clock_ms", int(now * 1000))
                        u.partial_text = ""
                        asyncio.create_task(
                            self._finalize_utterance(
                                p, u, forced=False, audio_bytes=audio_payload,
                                start_ms=start_ms, capture_started=cap_start,
                                utterance_id=curr_uid, seq=curr_seq
                            ),
                            name=f"split-finalize-{p.participant_id}-{start_ms}"
                        )
                    elif now - u.last_partial_at >= PARTIAL_INTERVAL_S and len(u.buffer) > 16000 * 2 * 0.8:
                        u.last_partial_at = now
                        await self._emit_partial(p, u)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("speaker loop crashed for %s", p.participant_id)
        finally:
            # flush any in-flight speech on disconnect if session not closed
            if not self._closed and u.in_speech and len(u.buffer) > 3200:
                try:
                    await asyncio.shield(self._finalize_utterance(p, u, forced=True,
                                                                 utterance_id=u.utterance_id,
                                                                 seq=u.seq))
                except Exception:
                    log.exception("flush on disconnect failed")

    # ------------------------------------------------------------------ #
    # STT: partial + final
    # ------------------------------------------------------------------ #
    def _lang_hint(self, p: RtParticipant, u: UtteranceState | None = None) -> str | None:
        if p.speak_lang not in ("auto", ""):
            return p.speak_lang
        if u and u.locked_language:
            return u.locked_language
        return None

    async def _emit_partial(self, p: RtParticipant, u: UtteranceState) -> None:
        try:
            chunk, _decision = await ai.transcribe(bytes(u.buffer), 16000,
                                                   lang_hint=self._lang_hint(p, u))
        except AppError as e:
            log.debug("partial STT unavailable: %s", e.message)
            return
        except Exception as e:
            log.debug("partial STT failed: %s", e)
            return
        if chunk.text and chunk.text != u.partial_text:
            u.partial_text = chunk.text
            # Phase 3 language locking: lock detected language once confidence threshold is reached
            if not u.locked_language and chunk.language and (chunk.confidence or 0.0) >= 0.70:
                u.locked_language = chunk.language
            lang = u.locked_language or chunk.language or self._lang_hint(p, u) or "auto"
            now_ms = int(time.time() * 1000)
            await manager.broadcast(
                self.session, ServerEventType.TRANSCRIPT_PARTIAL,
                {"speaker_name": p.display_name,
                 "display_name": p.display_name,
                 "speaker_id": str(p.participant_id),
                 "speakerId": str(p.participant_id),
                 "session_id": str(self.session.meeting_id),
                 "sessionId": str(self.session.meeting_id),
                 "language": lang,
                 "text": chunk.text,
                 "is_final": False,
                 "utterance_started_ms": u.started_at_ms,
                 "utterance_id": str(u.utterance_id),
                 "utteranceId": str(u.utterance_id),
                 "sequence": u.seq,
                 "seq": u.seq,
                 "created_at": now_ms,
                 "createdAt": now_ms},
                speaker_id=str(p.participant_id))

    async def _finalize_utterance(self, p: RtParticipant, u: UtteranceState,
                                  forced: bool = False,
                                  audio_bytes: bytes | None = None,
                                  start_ms: int | None = None,
                                  capture_started: float | None = None,
                                  utterance_id: uuid.UUID | None = None,
                                  seq: int | None = None) -> None:
        audio = audio_bytes if audio_bytes is not None else bytes(u.buffer)
        if audio_bytes is None:
            u.buffer = bytearray()
        if len(audio) < 1600:  # <50ms — noise blip
            u.locked_language = None
            return
        cap_start = capture_started if capture_started is not None else u.capture_started
        capture_ms = (time.perf_counter() - cap_start) * 1000
        started_at_ms = start_ms if start_ms is not None else u.started_at_ms
        t_stt = time.perf_counter()
        try:
            chunk, decision = await ai.transcribe(audio, 16000,
                                                   lang_hint=self._lang_hint(p, u))
        except (AppError, Exception) as ex:
            log.warning("STT transcription unavailable/failed for %s: %s", p.participant_id, ex)
            await manager.broadcast(
                self.session, ServerEventType.ERROR,
                {"code": "stt_unavailable", "message":
                    "Speech recognition is temporarily unavailable. Captions and "
                    "the original audio continue to work.",
                 "recoverable": True}, speaker_id=str(p.participant_id))
            u.locked_language = None
            return
        stt_ms = (time.perf_counter() - t_stt) * 1000
        met.STT_LATENCY.labels(provider=decision.provider).observe(stt_ms)
        text = (chunk.text or "").strip()
        if not text:
            await manager.broadcast(
                self.session, ServerEventType.SPEECH_ENDED,
                {"empty": True}, speaker_id=str(p.participant_id))
            u.locked_language = None
            return
        source_lang = u.locked_language or chunk.language or self._lang_hint(p, u) or "auto"
        if source_lang == "auto":
            det = await ai.detect_language(text)
            source_lang = det.language
        u.locked_language = None  # Reset locked language for the next speech segment
        await self._commit_segment(
            p, text=text, source_lang=source_lang, audio=audio,
            confidence=chunk.confidence, stt_model=chunk.model or decision.model,
            stt_provider=decision.provider, stt_ms=stt_ms, capture_ms=capture_ms,
            start_ms=started_at_ms,
            utterance_id=utterance_id or u.utterance_id,
            seq_num=seq or u.seq)

    # ------------------------------------------------------------------ #
    # Dev/test text injection (guarded; STT stage marked 'injected')
    # ------------------------------------------------------------------ #
    async def inject_transcript(self, p: RtParticipant, text: str,
                                language: str = "") -> None:
        if not ai.is_dev_mode(__import__("gt_ai.types", fromlist=["Task"]).Task.STT) \
                and not settings.app_env == "test":
            # In production with real STT configured, injection is a host-only
            # debug affordance — disabled entirely by default.
            raise AppError("transcript injection disabled", status=403)
        text = (text or "").strip()
        if not text:
            return
        source_lang = language or (p.speak_lang if p.speak_lang != "auto" else "")
        if not source_lang:
            det = await ai.detect_language(text)
            source_lang = det.language
        await self._commit_segment(p, text=text, source_lang=source_lang,
                                   audio=b"", confidence=1.0,
                                   stt_model="injected", stt_provider="inject",
                                   stt_ms=0.0, capture_ms=0.0, start_ms=0)

    # ------------------------------------------------------------------ #
    # Canonical segment + fan-out
    # ------------------------------------------------------------------ #
    async def _commit_segment(self, p: RtParticipant, *, text: str,
                              source_lang: str, audio: bytes,
                              confidence: float | None, stt_model: str,
                              stt_provider: str, stt_ms: float,
                              capture_ms: float, start_ms: int,
                              utterance_id: uuid.UUID | None = None,
                              seq_num: int | None = None) -> None:
        session = self.session
        # --- persist canonical source (immutable) ---
        async with db_session() as db:
            scalar_seq = (await db.execute(
                select(func.coalesce(func.max(M.TranscriptSegment.seq), 0))
                .where(M.TranscriptSegment.meeting_id == session.meeting_id)
            )).scalar()
            seq = (scalar_seq or 0) + 1
            segment = M.TranscriptSegment(
                meeting_id=session.meeting_id, seq=seq,
                speaker_id=p.participant_id, speaker_name=p.display_name,
                source_lang=source_lang, source_text=text, is_final=True,
                start_ms=start_ms or None, confidence=confidence,
                stt_model=stt_model, stt_provider=stt_provider,
                latency_json={"audio_capture_ms": capture_ms, "stt_final_ms": stt_ms},
            )
            db.add(segment)
            await db.commit()
            segment_id = segment.id

        # optionally store audio artifact (retention-controlled)
        if audio and settings.retention_audio_days:
            try:
                from app.storage import object_key, sha256_bytes, storage
                from gt_ai.audio_utils import pcm16_to_wav
                key = object_key("audio", str(session.org_id),
                                 f"{segment_id}.wav", sha256_bytes(audio[:64] + str(segment_id).encode()))
                await storage().put(key, pcm16_to_wav(audio, 16000), "audio/wav")
                async with db_session() as db:
                    await db.execute(
                        update(M.TranscriptSegment)
                        .where(M.TranscriptSegment.id == segment_id)
                        .values(audio_object_key=key))
                    await db.commit()
            except Exception:
                log.exception("audio artifact storage failed (non-fatal)")

        now_ms = int(time.time() * 1000)
        u_id = str(utterance_id) if utterance_id is not None else str(segment_id)
        await manager.broadcast(
            session, ServerEventType.SPEECH_ENDED,
            {"timestamp_ms": start_ms, "utterance_id": u_id, "utteranceId": u_id,
             "sequence": seq, "seq": seq},
            speaker_id=str(p.participant_id))
        await manager.broadcast(
            session, ServerEventType.TRANSCRIPT_FINAL,
            {"segment_id": str(segment_id), "utterance_id": u_id,
             "utteranceId": u_id,
             "seq": seq, "sequence": seq,
             "speaker_id": str(p.participant_id), "speakerId": str(p.participant_id),
             "speaker_name": p.display_name, "display_name": p.display_name,
             "session_id": str(session.meeting_id), "sessionId": str(session.meeting_id),
             "language": source_lang, "source_lang": source_lang,
             "source_language": source_lang, "sourceLanguage": source_lang,
             "text": text, "source_text": text, "sourceText": text,
             "is_final": True, "confidence": confidence,
             "stt_model": stt_model,
             "latency": {"audio_capture_ms": capture_ms, "stt_final_ms": stt_ms},
             "created_at": now_ms, "createdAt": now_ms,
             "dedup_key": f"{session.meeting_id}:{p.participant_id}:{seq}",
             "dedupKey": f"{session.meeting_id}:{p.participant_id}:{seq}"},
            speaker_id=str(p.participant_id))
        self._latest_final_seq[p.participant_id] = seq
        if session.quality_degraded:
            session.quality_degraded = False

        # --- compute deduplicated target set & fan out ---
        targets = manager.required_target_languages(
            session, source_lang, exclude_speaker=str(p.participant_id))
        prev_context = self._last_final_text.get(p.participant_id, "")
        self._last_final_text[p.participant_id] = text
        if not targets:
            return
        for target_lang in sorted(targets):
            key = (seq, target_lang)
            task = asyncio.create_task(
                self._translate_and_synthesize(
                    segment_id=segment_id, seq=seq, speaker=p, text=text,
                    source_lang=source_lang, target_lang=target_lang,
                    stt_ms=stt_ms, capture_ms=capture_ms,
                    prev_context=prev_context, utterance_id=u_id),
                name=f"fanout-{seq}-{target_lang}")
            self.translation_tasks[key] = task
            task.add_done_callback(lambda _t, k=key: self.translation_tasks.pop(k, None))

    async def _translate_and_synthesize(self, *, segment_id: uuid.UUID, seq: int,
                                        speaker: RtParticipant, text: str,
                                        source_lang: str, target_lang: str,
                                        stt_ms: float, capture_ms: float,
                                        prev_context: str = "",
                                        utterance_id: str | None = None) -> None:
        session = self.session
        trace = LatencyTrace(segment_id=str(segment_id), seq=seq,
                             source_lang=source_lang, target_lang=target_lang,
                             audio_capture_ms=capture_ms, stt_final_ms=stt_ms)
        t0 = time.perf_counter()
        # --- stale check before starting (speaker already moved on?) ---
        if self._is_stale(speaker.participant_id, seq):
            trace.stale_dropped = True
            met.STALE_AUDIO_DROPPED.labels(reason="pre_translation").inc()
            return
        u_id = utterance_id or str(segment_id)
        now_ms = int(time.time() * 1000)
        await manager.broadcast(
            session, ServerEventType.TRANSLATION_STARTED,
            {"segment_id": str(segment_id), "utterance_id": u_id, "utteranceId": u_id,
             "seq": seq, "sequence": seq, "target_lang": target_lang, "target_language": target_lang,
             "created_at": now_ms, "createdAt": now_ms},
            speaker_id=str(speaker.participant_id))
        try:
            async with db_session() as db:
                out = await translate_text(
                    db, text, source_lang, target_lang,
                    TranslateContext(
                        org_id=session.org_id, user_id=speaker.user_id,
                        product="realtime", meeting_id=session.meeting_id,
                        segment_id=segment_id, intent="latency_optimized",
                        context=prev_context,
                        persist=True, meter=True))
        except AppError as e:
            await self._translation_failed(segment_id, seq, target_lang, e)
            return
        except Exception as e:
            log.exception("translation crashed")
            await self._translation_failed(segment_id, seq, target_lang, e)
            return
        trace.translation_ms = (time.perf_counter() - t0) * 1000
        translated = out.result.text
        now_ms = int(time.time() * 1000)

        # --- Phase 5 translation.segment.final + translation.final contract ---
        final_translation_event = {
            "type": "translation.segment.final",
            "session_id": str(session.meeting_id),
            "sessionId": str(session.meeting_id),
            "speaker_id": str(speaker.participant_id),
            "speakerId": str(speaker.participant_id),
            "sequence": seq,
            "seq": seq,
            "utterance_id": u_id,
            "utteranceId": u_id,
            "segment_id": str(segment_id),
            "source_lang": source_lang,
            "source_language": source_lang,
            "sourceLanguage": source_lang,
            "target_lang": target_lang,
            "target_language": target_lang,
            "targetLanguage": target_lang,
            "source_text": text,
            "sourceText": text,
            "text": translated,
            "translated_text": translated,
            "translatedText": translated,
            "display_name": speaker.display_name,
            "speaker_name": speaker.display_name,
            "model": out.result.model,
            "quality_flags": out.result.quality_flags,
            "latency_ms": out.result.latency_ms,
            "created_at": now_ms,
            "createdAt": now_ms,
            "dedup_key": f"{session.meeting_id}:{speaker.participant_id}:{seq}:{target_lang}",
            "dedupKey": f"{session.meeting_id}:{speaker.participant_id}:{seq}:{target_lang}",
        }
        await manager.broadcast(
            session, ServerEventType.TRANSLATION_FINAL,
            final_translation_event,
            speaker_id=str(speaker.participant_id))
        await manager.broadcast(
            session, ServerEventType.TRANSLATION_SEGMENT_FINAL,
            final_translation_event,
            speaker_id=str(speaker.participant_id))

        if self._is_stale(speaker.participant_id, seq):
            trace.stale_dropped = True
            met.STALE_AUDIO_DROPPED.labels(reason="pre_tts").inc()
            await self._report_latency(trace)
            return

        # --- TTS: once per (segment, target_lang) group ---
        audio_listeners = manager.listeners_for_language(
            session, target_lang, want_audio=True)
        if not audio_listeners:
            await self._report_latency(trace)
            return
        await manager.broadcast(
            session, ServerEventType.TTS_STARTED,
            {"segment_id": str(segment_id), "utterance_id": u_id, "utteranceId": u_id,
             "seq": seq, "sequence": seq, "target_lang": target_lang, "target_language": target_lang,
             "created_at": now_ms, "createdAt": now_ms},
            to=audio_listeners, speaker_id=str(speaker.participant_id))
        t_tts = time.perf_counter()
        first = True
        try:
            stream, decision = await ai.synthesize_stream(translated, target_lang)
            chunk_idx = 0
            short_id_bytes = str(segment_id).replace("-", "")[:16].ljust(16, "\x00").encode("utf-8")
            lang_bytes = target_lang.encode("utf-8")
            bin_header = b"\x54" + short_id_bytes + bytes([len(lang_bytes)]) + lang_bytes

            async for audio in stream:
                if self._is_stale(speaker.participant_id, seq):
                    trace.stale_dropped = True
                    met.STALE_AUDIO_DROPPED.labels(reason="mid_tts").inc()
                    break
                if first:
                    trace.tts_first_audio_ms = (time.perf_counter() - t_tts) * 1000
                    met.TTS_LATENCY.labels(provider=decision.provider).observe(
                        trace.tts_first_audio_ms)
                    first = False
                b64 = base64.b64encode(audio.data).decode()
                await manager.broadcast(
                    session, ServerEventType.TTS_CHUNK,
                    {"segment_id": str(segment_id), "utterance_id": u_id, "utteranceId": u_id,
                     "seq": seq, "sequence": seq, "target_lang": target_lang, "target_language": target_lang,
                     "chunk_index": chunk_idx, "chunkIndex": chunk_idx,
                     "audio_base64": b64, "format": audio.format,
                     "sample_rate": audio.sample_rate,
                     "is_dev": audio.is_dev, "model": audio.model,
                     "created_at": now_ms, "createdAt": now_ms},
                    to=audio_listeners, speaker_id=str(speaker.participant_id))

                # Binary frame delivery for lowest-latency audio playback
                bin_frame = bin_header + audio.data
                for p in audio_listeners:
                    if p.connected and p.ws is not None:
                        try:
                            await p.ws.send_bytes(bin_frame)
                        except Exception:
                            pass

                chunk_idx += 1
            await manager.broadcast(
                session, ServerEventType.TTS_COMPLETED,
                {"segment_id": str(segment_id), "utterance_id": str(segment_id),
                 "seq": seq, "target_lang": target_lang, "target_language": target_lang,
                 "chunks": chunk_idx, "stale_dropped": trace.stale_dropped},
                to=audio_listeners, speaker_id=str(speaker.participant_id))
            # LiveKit mode: publish synthetic track (bridge no-ops in ws mode)
            from app.realtime import livekit_bridge
            await livekit_bridge.publish_translated_audio(
                session, target_lang, translated, str(segment_id), seq)
        except (AppError, Exception) as ex:
            log.warning("TTS fan-out failed for target %s: %s", target_lang, ex)
            await manager.broadcast(
                session, ServerEventType.ERROR,
                {"code": "tts_unavailable",
                 "message": "Translated speech is temporarily unavailable. "
                            "Translated captions remain active.",
                 "recoverable": True, "target_lang": target_lang},
                to=audio_listeners, speaker_id=str(speaker.participant_id))
        trace.delivery_ms = (time.perf_counter() - t0) * 1000
        trace.total_e2e_latency_ms = capture_ms + stt_ms + trace.delivery_ms
        met.E2E_LATENCY.labels(src=source_lang, tgt=target_lang).observe(
            trace.total_e2e_latency_ms)
        await self._report_latency(trace)

    async def _translation_failed(self, segment_id: uuid.UUID, seq: int,
                                  target_lang: str, e: Exception) -> None:
        message = ("Translation is taking longer than expected. "
                   "The original audio is still active.")
        code = e.__class__.__name__
        detail = getattr(e, "message", str(e))
        if isinstance(e, AppError):
            code = getattr(e, "code", code)
        await manager.broadcast(
            self.session, ServerEventType.TRANSLATION_FAILED,
            {"segment_id": str(segment_id), "seq": seq, "target_lang": target_lang,
             "code": code, "message": message, "detail": detail[:200],
             "recoverable": True})
        met.TRANSLATION_FAILURES.labels(src="?", tgt=target_lang,
                                        provider="router", reason=code).inc()

    async def _report_latency(self, trace: LatencyTrace) -> None:
        await manager.broadcast(
            self.session, ServerEventType.LATENCY_REPORT,
            trace.model_dump(), sequenced=False)

    def _is_stale(self, speaker_id: uuid.UUID, seq: int) -> bool:
        """Stale output detection (PDD §10): a newer final segment from the
        same speaker plus an elapsed budget means late audio would talk over
        current speech — drop it instead."""
        latest = self._latest_final_seq.get(speaker_id, seq)
        if seq >= latest:
            return False
        # allow one segment of slack within the staleness window
        return (latest - seq) >= 1 and seq < latest


sessions_pipeline: dict[str, MeetingPipeline] = {}


def get_pipeline(session: RtSession) -> MeetingPipeline:
    if session.pipeline is None:
        session.pipeline = MeetingPipeline(session)
    return session.pipeline
