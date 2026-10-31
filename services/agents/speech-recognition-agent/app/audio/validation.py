"""Audio validation engine for Speech Recognition Agent."""
from __future__ import annotations

from typing import Optional
from app.core.exceptions import AudioValidationError


class AudioValidator:
    """Validates incoming audio bytes against sample rate, channels, and duration limits."""

    SUPPORTED_SAMPLE_RATES = {8000, 16000, 22050, 24000, 32000, 44100, 48000}
    CANONICAL_RATE = 16000

    def __init__(self, max_duration_sec: float = 3600.0):
        self.max_duration_sec = max_duration_sec

    def validate_pcm16(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        channels: int = 1,
        max_duration_sec: Optional[float] = None,
    ) -> None:
        """Validates raw PCM16 audio bytes."""
        if not audio_bytes:
            raise AudioValidationError("Audio payload is empty")

        if sample_rate not in self.SUPPORTED_SAMPLE_RATES:
            raise AudioValidationError(
                f"Unsupported sample rate: {sample_rate}Hz. Supported: {self.SUPPORTED_SAMPLE_RATES}"
            )

        # PCM16 requires 2 bytes per sample per channel
        bytes_per_sample = 2 * channels
        if len(audio_bytes) % bytes_per_sample != 0:
            raise AudioValidationError(
                f"Audio byte length ({len(audio_bytes)}) is not aligned with 16-bit {channels}-channel PCM"
            )

        # Duration check
        limit = max_duration_sec if max_duration_sec is not None else self.max_duration_sec
        duration_sec = len(audio_bytes) / (sample_rate * bytes_per_sample)
        if duration_sec > limit:
            raise AudioValidationError(
                f"Audio duration ({duration_sec:.2f}s) exceeds maximum allowed limit ({limit:.1f}s)"
            )
