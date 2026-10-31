"""High-level audio processor coordinator for batch files and real-time sessions."""
from __future__ import annotations

import io
import time
import uuid
import numpy as np
import soundfile as sf
from app.audio.normalization import AudioNormalizer
from app.audio.quality import AudioQualityAnalyzer
from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import AudioChunk, AudioProcessResponse, AudioQualityMetrics
from app.services.pipeline import AudioPipeline
from app.services.session_manager import SessionManager

log = get_logger("processor")


class AudioProcessorService:
    """Coordinates batch file processing and session streaming."""

    def __init__(self):
        self.session_manager = SessionManager(
            max_concurrent_sessions=settings.streaming.max_concurrent_sessions,
            queue_capacity=settings.streaming.queue_capacity,
        )
        self.normalizer = AudioNormalizer(
            target_sample_rate=settings.audio.sample_rate,
            target_channels=settings.audio.channels,
        )
        self.quality_analyzer = AudioQualityAnalyzer(
            snr_warning_threshold_db=settings.quality.snr_warning_threshold_db,
            clipping_warning_ratio=settings.quality.clipping_warning_ratio,
            silence_warning_ratio=settings.quality.silence_warning_ratio,
        )

    async def process_audio_file(
        self,
        file_bytes: bytes,
        filename: str = "audio.wav",
        session_id: str | None = None,
        conversation_id: str | None = None,
        speaker_id: str = "user_test",
    ) -> AudioProcessResponse:
        """Processes a complete audio file in streaming 50ms frames and returns segmentation response."""
        t_start = time.perf_counter()
        session_id = session_id or f"sess_{uuid.uuid4().hex[:10]}"
        conversation_id = conversation_id or session_id

        # Read audio with soundfile
        try:
            with sf.SoundFile(io.BytesIO(file_bytes)) as audio_file:
                sr = audio_file.samplerate
                channels = audio_file.channels
                frames_data = audio_file.read(dtype="int16")
                pcm_bytes = frames_data.tobytes()
        except Exception as exc:
            # Fallback to interpreting as raw PCM16 mono 16kHz
            log.warning(f"Could not parse soundfile container ({exc}), attempting raw PCM16 parsing.")
            pcm_bytes = file_bytes
            sr = 16000
            channels = 1

        # Normalize to canonical 16kHz mono
        canonical_pcm = self.normalizer.normalize(
            pcm_bytes=pcm_bytes,
            source_sample_rate=sr,
            source_channels=channels,
        )

        total_audio_ms = len(canonical_pcm) // 32  # 32 bytes per ms @ 16kHz mono int16

        # Frame parameters
        frame_bytes_len = (16000 * 50 // 1000) * 2  # 1600 bytes = 50ms
        collected_chunks: list[AudioChunk] = []

        pipeline = AudioPipeline(
            session_id=session_id,
            conversation_id=conversation_id,
            speaker_id=speaker_id,
        )

        # Slice into 50ms frames and stream through pipeline
        offset = 0
        seq = 0
        while offset < len(canonical_pcm):
            frame = canonical_pcm[offset:offset + frame_bytes_len]
            if len(frame) < frame_bytes_len:
                # Pad last frame with zero silence to maintain exact 50ms alignment
                frame = frame.ljust(frame_bytes_len, b"\x00")

            events = await pipeline.process_frame(
                raw_bytes=frame,
                sequence=seq,
                sample_rate=16000,
                channels=1,
                encoding="pcm_s16le",
            )

            for evt, pcm_data in events:
                if evt.get("event") == "audio.segment.final":
                    # Reconstruct chunk model
                    collected_chunks.append(
                        AudioChunk(
                            session_id=evt["session_id"],
                            conversation_id=evt["conversation_id"],
                            speaker_id=evt["speaker_id"],
                            segment_id=evt["segment_id"],
                            sequence=evt["sequence"],
                            start_ms=evt["start_ms"],
                            end_ms=evt["end_ms"],
                            duration_ms=evt["duration_ms"],
                            sample_rate=evt["sample_rate"],
                            channels=evt["channels"],
                            encoding=evt["encoding"],
                            quality=AudioQualityMetrics(**evt["quality"]),
                            status="final",
                            storage_ref=evt.get("storage_ref"),
                        )
                    )
            offset += frame_bytes_len
            seq += 1

        # Final flush
        flush_events = pipeline.flush()
        for evt, pcm_data in flush_events:
            if evt.get("event") == "audio.segment.final":
                collected_chunks.append(
                    AudioChunk(
                        session_id=evt["session_id"],
                        conversation_id=evt["conversation_id"],
                        speaker_id=evt["speaker_id"],
                        segment_id=evt["segment_id"],
                        sequence=evt["sequence"],
                        start_ms=evt["start_ms"],
                        end_ms=evt["end_ms"],
                        duration_ms=evt["duration_ms"],
                        sample_rate=evt["sample_rate"],
                        channels=evt["channels"],
                        encoding=evt["encoding"],
                        quality=AudioQualityMetrics(**evt["quality"]),
                        status="final",
                        storage_ref=evt.get("storage_ref"),
                    )
                )

        # Overall quality summary
        speech_ms_total = sum(c.duration_ms for c in collected_chunks)
        overall_quality = self.quality_analyzer.analyze(
            pcm_bytes=canonical_pcm,
            speech_duration_ms=speech_ms_total,
            sample_rate=16000,
        )

        t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        return AudioProcessResponse(
            session_id=session_id,
            total_audio_duration_ms=total_audio_ms,
            speech_duration_ms=speech_ms_total,
            segments_count=len(collected_chunks),
            segments=collected_chunks,
            overall_quality=overall_quality,
            processing_time_ms=round(t_elapsed_ms, 2),
        )


audio_processor = AudioProcessorService()

