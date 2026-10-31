"""Core single-session Audio Pipeline coordinating ingestion, VAD, denoising, and segmentation."""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from app.audio.chunk_manager import ChunkManager
from app.audio.ingestion import AudioIngestionEngine
from app.audio.normalization import AudioNormalizer
from app.audio.quality import AudioQualityAnalyzer
from app.audio.segmentation import SegmentBuffer, SpeechSegmenter
from app.audio.validation import AudioValidator
from app.core.config import settings
from app.core.logging import get_logger
from app.models.events import (
    AudioSegmentFinalEvent,
    AudioSegmentPartialEvent,
    SpeechEndedEvent,
    SpeechStartedEvent,
)
from app.models.schemas import AudioChunk, AudioQualityMetrics
from app.monitoring.metrics import metrics
from app.providers.noise_suppression import get_noise_suppressor
from app.providers.vad import get_vad_provider
from app.services.intelligence_agent import AcousticIntelligenceAgent

log = get_logger("pipeline")


class AudioPipeline:
    """Real-time processing pipeline for a single speaker / audio stream."""

    def __init__(
        self,
        session_id: str,
        conversation_id: str,
        speaker_id: str,
        on_event_callback: Optional[Callable[[Dict[str, Any], Optional[bytes]], Any]] = None,
    ):
        self.session_id = session_id
        self.conversation_id = conversation_id
        self.speaker_id = speaker_id
        self.on_event = on_event_callback

        # Audio processors
        self.validator = AudioValidator(
            canonical_sample_rate=settings.audio.sample_rate,
            canonical_channels=settings.audio.channels,
            expected_frame_duration_ms=settings.audio.frame_duration_ms,
            max_frame_size_bytes=settings.audio.max_frame_size_bytes,
        )
        self.normalizer = AudioNormalizer(
            target_sample_rate=settings.audio.sample_rate,
            target_channels=settings.audio.channels,
        )
        self.ingestion = AudioIngestionEngine(
            validator=self.validator,
            normalizer=self.normalizer,
            canonical_sample_rate=settings.audio.sample_rate,
            canonical_channels=settings.audio.channels,
        )
        self.denoiser = get_noise_suppressor(
            name=settings.noise_suppression.provider,
            enabled=settings.noise_suppression.enabled,
        )
        self.vad = get_vad_provider(
            name=settings.vad.provider,
            sensitivity=settings.vad.sensitivity,
        )
        self.segmenter = SpeechSegmenter(
            speech_threshold=settings.vad.speech_threshold,
            silence_threshold=settings.vad.silence_threshold,
            min_speech_duration_ms=settings.vad.min_speech_duration_ms,
            min_silence_duration_ms=settings.vad.min_silence_duration_ms,
            max_utterance_duration_ms=settings.vad.max_utterance_duration_ms,
            partial_processing_interval_ms=settings.vad.partial_processing_interval_ms,
            phrase_commit_interval_ms=settings.vad.phrase_commit_interval_ms,
            hangover_duration_ms=settings.vad.hangover_duration_ms,
        )
        self.quality_analyzer = AudioQualityAnalyzer(
            snr_warning_threshold_db=settings.quality.snr_warning_threshold_db,
            clipping_warning_ratio=settings.quality.clipping_warning_ratio,
            silence_warning_ratio=settings.quality.silence_warning_ratio,
            min_confidence_good=settings.quality.min_confidence_good,
            min_confidence_fair=settings.quality.min_confidence_fair,
        )
        self.chunk_manager = ChunkManager(
            retention_policy=settings.audio.retention_policy,
            temp_dir=settings.audio.temp_storage_dir,
        )
        self.intelligence_agent = AcousticIntelligenceAgent()

        self.clock_ms = 0
        self.frames_processed = 0
        self._last_speech_prob = 0.0
        self.last_quality: Optional[AudioQualityMetrics] = None

    async def process_frame(
        self,
        raw_bytes: bytes,
        sequence: int = -1,
        sample_rate: int = 16000,
        channels: int = 1,
        encoding: str = "pcm_s16le",
    ) -> List[Tuple[Dict[str, Any], Optional[bytes]]]:
        """Processes one audio frame end-to-end and returns generated events and binary payloads."""
        t_start = time.perf_counter()
        emitted_events: List[Tuple[Dict[str, Any], Optional[bytes]]] = []

        # 1. Ingestion, Validation & Normalization
        canonical_pcm, seq_status = self.ingestion.ingest_frame(
            raw_bytes=raw_bytes,
            sequence=sequence,
            sample_rate=sample_rate,
            channels=channels,
            encoding=encoding,
        )
        if not canonical_pcm:
            # Duplicate, gap, or invalid frame
            if seq_status == "duplicate":
                metrics.record_dropped_frame("duplicate")
            return emitted_events

        # 2. VAD Inference
        t_vad = time.perf_counter()
        speech_prob = self.vad.process_chunk(canonical_pcm, settings.audio.sample_rate)
        self._last_speech_prob = speech_prob
        metrics.observe_vad_latency((time.perf_counter() - t_vad) * 1000.0)

        is_speech = speech_prob >= settings.vad.speech_threshold

        # 3. Noise Suppression
        t_denoise = time.perf_counter()
        cleaned_pcm = self.denoiser.process_frame(
            pcm_bytes=canonical_pcm,
            sample_rate=settings.audio.sample_rate,
            is_speech=is_speech,
        )
        metrics.observe_denoise_latency((time.perf_counter() - t_denoise) * 1000.0)

        # 4. Speech Segmentation & State Decisions
        t_seg = time.perf_counter()
        speech_evt, partial_buf, final_buf = self.segmenter.process_frame(
            frame_bytes=cleaned_pcm,
            speech_probability=speech_prob,
            clock_ms=self.clock_ms,
            frame_duration_ms=settings.audio.frame_duration_ms,
        )
        metrics.observe_segmentation_latency((time.perf_counter() - t_seg) * 1000.0)

        # Handle speech started
        if speech_evt == "speech.started" and self.segmenter._current_buffer:
            seg_id = self.segmenter._current_buffer.segment_id
            log.info(f"Speech started: speaker {self.speaker_id} (segment {seg_id})")
            start_event = SpeechStartedEvent(
                session_id=self.session_id,
                conversation_id=self.conversation_id,
                speaker_id=self.speaker_id,
                sequence=self.frames_processed,
                mono_ms=self.clock_ms,
                segment_id=seg_id,
            ).model_dump()
            emitted_events.append((start_event, None))

        # Handle incremental partial segment emission
        if partial_buf is not None:
            pcm_payload = partial_buf.pcm_bytes
            q_metrics = self.quality_analyzer.analyze(
                pcm_bytes=pcm_payload,
                speech_duration_ms=partial_buf.speech_duration_ms,
                sample_rate=settings.audio.sample_rate,
            )
            self.last_quality = q_metrics
            metrics.observe_snr(q_metrics.snr_db)

            chunk = self.chunk_manager.create_chunk(
                session_id=self.session_id,
                conversation_id=self.conversation_id,
                speaker_id=self.speaker_id,
                segment_id=partial_buf.segment_id,
                sequence=partial_buf.sequence,
                start_ms=partial_buf.start_ms,
                end_ms=self.clock_ms,
                pcm_bytes=pcm_payload,
                quality=q_metrics,
                status="partial",
            )
            metrics.record_segment("partial")
            log.debug(f"Partial segment emitted: {chunk.segment_id} ({chunk.duration_ms} ms)")

            partial_event = AudioSegmentPartialEvent(
                session_id=self.session_id,
                conversation_id=self.conversation_id,
                speaker_id=self.speaker_id,
                sequence=partial_buf.sequence,
                segment_id=chunk.segment_id,
                start_ms=chunk.start_ms,
                end_ms=chunk.end_ms,
                duration_ms=chunk.duration_ms,
                sample_rate=chunk.sample_rate,
                channels=chunk.channels,
                encoding=chunk.encoding,
                quality=q_metrics.model_dump(),
                status="partial",
                storage_ref=chunk.storage_ref,
            ).model_dump()
            emitted_events.append((partial_event, pcm_payload))

        # Handle final committed segment
        if final_buf is not None:
            pcm_payload = final_buf.pcm_bytes
            q_metrics = self.quality_analyzer.analyze(
                pcm_bytes=pcm_payload,
                speech_duration_ms=final_buf.speech_duration_ms,
                sample_rate=settings.audio.sample_rate,
            )
            self.last_quality = q_metrics
            metrics.observe_snr(q_metrics.snr_db)

            chunk = self.chunk_manager.create_chunk(
                session_id=self.session_id,
                conversation_id=self.conversation_id,
                speaker_id=self.speaker_id,
                segment_id=final_buf.segment_id,
                sequence=final_buf.sequence,
                start_ms=final_buf.start_ms,
                end_ms=self.clock_ms,
                pcm_bytes=pcm_payload,
                quality=q_metrics,
                status="final",
            )
            metrics.record_segment("final")

            log.info(
                f"Final audio segment committed: {chunk.segment_id} ({chunk.duration_ms} ms) "
                f"Quality: {q_metrics.quality_status.upper()} (SNR {q_metrics.snr_db} dB)"
            )

            # Speech ended event
            if speech_evt == "speech.ended":
                ended_event = SpeechEndedEvent(
                    session_id=self.session_id,
                    conversation_id=self.conversation_id,
                    speaker_id=self.speaker_id,
                    sequence=self.frames_processed,
                    duration_ms=chunk.duration_ms,
                    segment_id=chunk.segment_id,
                ).model_dump()
                emitted_events.append((ended_event, None))

            final_event = AudioSegmentFinalEvent(
                session_id=self.session_id,
                conversation_id=self.conversation_id,
                speaker_id=self.speaker_id,
                sequence=final_buf.sequence,
                segment_id=chunk.segment_id,
                start_ms=chunk.start_ms,
                end_ms=chunk.end_ms,
                duration_ms=chunk.duration_ms,
                sample_rate=chunk.sample_rate,
                channels=chunk.channels,
                encoding=chunk.encoding,
                quality=q_metrics.model_dump(),
                status="final",
                storage_ref=chunk.storage_ref,
            ).model_dump()
            emitted_events.append((final_event, pcm_payload))

            # Trigger background OpenAI Agents SDK Acoustic Intelligence analysis
            import asyncio
            asyncio.create_task(self.intelligence_agent.analyze_segment(chunk))

        # Advance internal frame clock
        self.clock_ms += settings.audio.frame_duration_ms
        self.frames_processed += 1
        metrics.record_frame(self.session_id)

        t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        metrics.observe_frame_latency(t_elapsed_ms)

        # Dispatch callbacks if registered
        if self.on_event:
            for evt, pcm in emitted_events:
                try:
                    res = self.on_event(evt, pcm)
                    if hasattr(res, "__await__"):
                        import asyncio
                        asyncio.create_task(res)
                except Exception as exc:
                    log.error(f"Event callback error: {exc}")

        # Automatically forward finalized audio segments to Agent 02 (Speech Recognition)
        for evt, pcm in emitted_events:
            if evt.get("event") == "audio.segment.final":
                from app.integration.event_publisher import publisher
                import asyncio
                asyncio.create_task(publisher.publish_event(evt, pcm))

        return emitted_events

    def flush(self) -> List[Tuple[Dict[str, Any], Optional[bytes]]]:
        """Flushes remaining audio on stream completion or disconnect."""
        emitted: List[Tuple[Dict[str, Any], Optional[bytes]]] = []
        buf = self.segmenter.force_flush(self.clock_ms)
        if buf is not None:
            pcm = buf.pcm_bytes
            q = self.quality_analyzer.analyze(
                pcm_bytes=pcm,
                speech_duration_ms=buf.speech_duration_ms,
                sample_rate=settings.audio.sample_rate,
            )
            chunk = self.chunk_manager.create_chunk(
                session_id=self.session_id,
                conversation_id=self.conversation_id,
                speaker_id=self.speaker_id,
                segment_id=buf.segment_id,
                sequence=buf.sequence,
                start_ms=buf.start_ms,
                end_ms=self.clock_ms,
                pcm_bytes=pcm,
                quality=q,
                status="final",
            )
            final_event = AudioSegmentFinalEvent(
                session_id=self.session_id,
                conversation_id=self.conversation_id,
                speaker_id=self.speaker_id,
                sequence=buf.sequence,
                segment_id=chunk.segment_id,
                start_ms=chunk.start_ms,
                end_ms=chunk.end_ms,
                duration_ms=chunk.duration_ms,
                sample_rate=chunk.sample_rate,
                channels=chunk.channels,
                encoding=chunk.encoding,
                quality=q.model_dump(),
                status="final",
                storage_ref=chunk.storage_ref,
            ).model_dump()
            emitted.append((final_event, pcm))

        # Forward flushed finalized segments to Agent 02
        for evt, pcm in emitted:
            if evt.get("event") == "audio.segment.final":
                from app.integration.event_publisher import publisher
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(publisher.publish_event(evt, pcm))
                except RuntimeError:
                    pass

        return emitted

