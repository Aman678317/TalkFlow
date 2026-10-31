"""Audio ingestion engine coordinating frame validation and normalization."""
from __future__ import annotations

from typing import Tuple
from app.audio.normalization import AudioNormalizer
from app.audio.validation import AudioValidator
from app.core.exceptions import AudioValidationError


class AudioIngestionEngine:
    """Ingests raw incoming audio frames from WebSocket, LiveKit, or files."""

    def __init__(
        self,
        validator: AudioValidator | None = None,
        normalizer: AudioNormalizer | None = None,
        canonical_sample_rate: int = 16000,
        canonical_channels: int = 1,
    ):
        self.validator = validator or AudioValidator(
            canonical_sample_rate=canonical_sample_rate,
            canonical_channels=canonical_channels,
        )
        self.normalizer = normalizer or AudioNormalizer(
            target_sample_rate=canonical_sample_rate,
            target_channels=canonical_channels,
        )
        self.canonical_sample_rate = canonical_sample_rate
        self.canonical_channels = canonical_channels
        self._last_sequence = -1

    def ingest_frame(
        self,
        raw_bytes: bytes,
        sequence: int = -1,
        sample_rate: int = 16000,
        channels: int = 1,
        encoding: str = "pcm_s16le",
    ) -> Tuple[bytes, str]:
        """Validates and normalizes an incoming audio frame.
        
        Returns:
            Tuple of (canonical_pcm16_bytes, sequence_status)
        """
        # 1. Validate payload
        self.validator.validate_frame(
            frame_bytes=raw_bytes,
            sample_rate=sample_rate,
            channels=channels,
            encoding=encoding,
        )

        # 2. Sequence verification if provided
        seq_status = "valid"
        if sequence >= 0:
            is_valid, seq_status = self.validator.validate_sequence(sequence, self._last_sequence)
            if not is_valid:
                # Duplicate or out-of-order frame
                return b"", seq_status
            self._last_sequence = sequence

        # 3. Format Normalization (resampling & stereo-to-mono downmixing if necessary)
        canonical_pcm = self.normalizer.normalize(
            pcm_bytes=raw_bytes,
            source_sample_rate=sample_rate,
            source_channels=channels,
        )

        return canonical_pcm, seq_status

    def reset_sequence(self) -> None:
        """Resets sequence tracking for a new or reconnected stream."""
        self._last_sequence = -1

