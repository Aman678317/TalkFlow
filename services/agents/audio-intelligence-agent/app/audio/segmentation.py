"""Intelligent phrase-aware streaming speech segmentation."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple
from app.models.schemas import AudioChunk, AudioQualityMetrics


class SegmentationState(str, Enum):
    IDLE = "idle"
    IN_SPEECH = "in_speech"
    IN_HANGOVER = "in_hangover"


@dataclass
class SegmentBuffer:
    """Working buffer for an in-flight utterance segment."""
    segment_id: str
    sequence: int
    start_ms: int
    frames: List[bytes] = field(default_factory=list)
    speech_duration_ms: int = 0
    silence_duration_ms: int = 0
    last_partial_ms: int = 0
    last_commit_ms: int = 0

    @property
    def pcm_bytes(self) -> bytes:
        return b"".join(self.frames)

    @property
    def total_duration_ms(self) -> int:
        # For 16kHz mono PCM16: 32 bytes = 1 ms (16000 * 2 / 1000)
        return len(self.pcm_bytes) // 32


class SpeechSegmenter:
    """Manages real-time audio segmentation, hangover, pause detection, and chunk emission."""

    def __init__(
        self,
        speech_threshold: float = 0.5,
        silence_threshold: float = 0.35,
        min_speech_duration_ms: int = 250,
        min_silence_duration_ms: int = 500,
        max_utterance_duration_ms: int = 15000,
        partial_processing_interval_ms: int = 1200,
        phrase_commit_interval_ms: int = 4000,
        hangover_duration_ms: int = 600,
    ):
        self.speech_threshold = speech_threshold
        self.silence_threshold = silence_threshold
        self.min_speech_duration_ms = min_speech_duration_ms
        self.min_silence_duration_ms = min_silence_duration_ms
        self.max_utterance_duration_ms = max_utterance_duration_ms
        self.partial_processing_interval_ms = partial_processing_interval_ms
        self.phrase_commit_interval_ms = phrase_commit_interval_ms
        self.hangover_duration_ms = hangover_duration_ms

        self.state = SegmentationState.IDLE
        self._current_buffer: Optional[SegmentBuffer] = None
        self._segment_counter = 0

    @property
    def in_speech(self) -> bool:
        return self.state in (SegmentationState.IN_SPEECH, SegmentationState.IN_HANGOVER)

    def process_frame(
        self,
        frame_bytes: bytes,
        speech_probability: float,
        clock_ms: int,
        frame_duration_ms: int = 50,
    ) -> Tuple[
        Optional[str],  # event_type: "speech.started" | "speech.ended" | None
        Optional[SegmentBuffer],  # partial buffer ready for emission
        Optional[SegmentBuffer],  # final committed buffer
    ]:
        """Processes one audio frame with its VAD probability, returning segmentation decisions."""
        speech_event: Optional[str] = None
        partial_to_emit: Optional[SegmentBuffer] = None
        final_to_commit: Optional[SegmentBuffer] = None

        is_speech = speech_probability >= self.speech_threshold
        is_silence = speech_probability < self.silence_threshold

        # ---------------- State: IDLE ----------------
        if self.state == SegmentationState.IDLE:
            if is_speech:
                self.state = SegmentationState.IN_SPEECH
                self._segment_counter += 1
                segment_id = f"seg_{uuid.uuid4().hex[:12]}"
                self._current_buffer = SegmentBuffer(
                    segment_id=segment_id,
                    sequence=self._segment_counter,
                    start_ms=clock_ms,
                    frames=[frame_bytes],
                    speech_duration_ms=frame_duration_ms,
                    silence_duration_ms=0,
                )
                speech_event = "speech.started"
            return speech_event, partial_to_emit, final_to_commit

        # ---------------- State: IN_SPEECH / IN_HANGOVER ----------------
        buf = self._current_buffer
        assert buf is not None
        buf.frames.append(frame_bytes)

        if is_speech:
            self.state = SegmentationState.IN_SPEECH
            buf.speech_duration_ms += frame_duration_ms
            buf.silence_duration_ms = 0
        else:
            buf.silence_duration_ms += frame_duration_ms
            if is_silence:
                self.state = SegmentationState.IN_HANGOVER

        total_dur = buf.total_duration_ms

        # Trigger 1: Natural pause / Hangover expiration
        if buf.silence_duration_ms >= self.min_silence_duration_ms:
            if buf.speech_duration_ms >= self.min_speech_duration_ms:
                # Legitimate utterance completed
                final_to_commit = buf
                speech_event = "speech.ended"
            # Reset segmenter state
            self.state = SegmentationState.IDLE
            self._current_buffer = None
            return speech_event, partial_to_emit, final_to_commit

        # Trigger 2: Max utterance duration exceeded
        if total_dur >= self.max_utterance_duration_ms:
            final_to_commit = buf
            speech_event = "speech.ended"
            # Start seamless continuation segment
            self._segment_counter += 1
            new_id = f"seg_{uuid.uuid4().hex[:12]}"
            self.state = SegmentationState.IN_SPEECH
            self._current_buffer = SegmentBuffer(
                segment_id=new_id,
                sequence=self._segment_counter,
                start_ms=clock_ms + frame_duration_ms,
                frames=[],
                speech_duration_ms=0,
                silence_duration_ms=0,
            )
            return speech_event, partial_to_emit, final_to_commit

        # Trigger 3: Phrase boundary commit (long utterance with small pause dip)
        if (
            self.phrase_commit_interval_ms > 0
            and total_dur >= self.phrase_commit_interval_ms
            and buf.silence_duration_ms >= 250  # mini-pause clause boundary
            and buf.speech_duration_ms >= self.min_speech_duration_ms
        ):
            final_to_commit = buf
            self._segment_counter += 1
            new_id = f"seg_{uuid.uuid4().hex[:12]}"
            self.state = SegmentationState.IN_SPEECH
            self._current_buffer = SegmentBuffer(
                segment_id=new_id,
                sequence=self._segment_counter,
                start_ms=clock_ms + frame_duration_ms,
                frames=[],
                speech_duration_ms=0,
                silence_duration_ms=0,
            )
            return speech_event, partial_to_emit, final_to_commit

        # Trigger 4: Incremental partial emission during ongoing speech
        if (
            self.partial_processing_interval_ms > 0
            and total_dur - buf.last_partial_ms >= self.partial_processing_interval_ms
            and buf.speech_duration_ms >= self.min_speech_duration_ms
        ):
            buf.last_partial_ms = total_dur
            partial_to_emit = buf

        return speech_event, partial_to_emit, final_to_commit

    def force_flush(self, clock_ms: int) -> Optional[SegmentBuffer]:
        """Flushes any pending utterance buffer upon session disconnect or audio stop."""
        if self._current_buffer and self._current_buffer.speech_duration_ms >= self.min_speech_duration_ms:
            buf = self._current_buffer
            self.state = SegmentationState.IDLE
            self._current_buffer = None
            return buf
        self.state = SegmentationState.IDLE
        self._current_buffer = None
        return None

