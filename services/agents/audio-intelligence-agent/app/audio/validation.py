"""Audio frame and stream validation module."""
from __future__ import annotations

from typing import Tuple
from app.core.exceptions import (
    AudioValidationError,
    CorruptedFrameError,
    UnsupportedAudioFormatError,
)


class AudioValidator:
    """Validates raw audio frames and streaming sequence integrity."""

    def __init__(
        self,
        canonical_sample_rate: int = 16000,
        canonical_channels: int = 1,
        expected_frame_duration_ms: int = 50,
        max_frame_size_bytes: int = 8192,
    ):
        self.canonical_sample_rate = canonical_sample_rate
        self.canonical_channels = canonical_channels
        self.expected_frame_duration_ms = expected_frame_duration_ms
        self.max_frame_size_bytes = max_frame_size_bytes
        self.bytes_per_sample = 2  # 16-bit PCM

    def validate_frame(
        self,
        frame_bytes: bytes,
        sample_rate: int = 16000,
        channels: int = 1,
        encoding: str = "pcm_s16le",
    ) -> bool:
        """Validates that a frame conforms to format, alignment, and size bounds."""
        if not frame_bytes or len(frame_bytes) == 0:
            raise AudioValidationError("Audio frame is empty")

        if len(frame_bytes) > self.max_frame_size_bytes:
            raise AudioValidationError(
                f"Audio frame exceeds maximum allowable size: {len(frame_bytes)} > {self.max_frame_size_bytes}"
            )

        # Byte alignment check: int16 * channels requires an even number of bytes
        frame_alignment = self.bytes_per_sample * channels
        if len(frame_bytes) % frame_alignment != 0:
            raise CorruptedFrameError(
                f"Frame size {len(frame_bytes)} bytes is not aligned to {frame_alignment} bytes per multi-channel sample"
            )

        if sample_rate not in (8000, 16000, 22050, 24000, 32000, 44100, 48000):
            raise UnsupportedAudioFormatError(f"Unsupported sample rate: {sample_rate} Hz")

        if channels not in (1, 2):
            raise UnsupportedAudioFormatError(f"Unsupported channel count: {channels} (only mono/stereo supported)")

        if encoding.lower() not in ("pcm_s16le", "pcm_16", "pcm"):
            raise UnsupportedAudioFormatError(f"Unsupported audio encoding: {encoding} (only pcm_s16le supported)")

        return True

    def validate_sequence(
        self,
        current_seq: int,
        last_seq: int,
    ) -> Tuple[bool, str]:
        """Validates sequence monotonicity and detects gaps or duplicate frames."""
        if last_seq < 0:
            return True, "initial"

        if current_seq == last_seq:
            return False, "duplicate"

        if current_seq < last_seq:
            return False, "out_of_order"

        if current_seq > last_seq + 1:
            return True, f"gap_detected: skipped {current_seq - last_seq - 1} frames"

        return True, "valid"

