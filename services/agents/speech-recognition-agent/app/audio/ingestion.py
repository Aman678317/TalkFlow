"""Audio ingestion engine for Speech Recognition Agent."""
from __future__ import annotations

import base64
from typing import Optional, Tuple
from app.audio.conversion import resample_pcm16, wav_bytes_to_pcm16
from app.audio.validation import AudioValidator
from app.core.exceptions import AudioValidationError


class AudioIngestionEngine:
    """Ingests and normalizes incoming audio from WebSocket frames, REST payloads, and WAV files."""

    def __init__(self, validator: Optional[AudioValidator] = None):
        self.validator = validator or AudioValidator()

    def ingest_binary_frame(self, data: bytes) -> Tuple[str, bytes]:
        """Decodes TalkFlow binary frame layout:
        Byte 0     : 'O' (0x4F) original audio
        Bytes 1-16 : 16-char ASCII segment short-id
        Bytes 17.. : PCM16 mono @16kHz little-endian
        """
        if len(data) < 18:
            raise AudioValidationError(f"Binary frame too short ({len(data)} bytes, expected >= 18)")

        if data[0] == ord("O"):
            short_id = data[1:17].decode("ascii", errors="replace").rstrip("0").strip()
            pcm16 = data[17:]
            self.validator.validate_pcm16(pcm16, sample_rate=16000, channels=1)
            return short_id, pcm16

        # Standard raw PCM16 frame without header
        self.validator.validate_pcm16(data, sample_rate=16000, channels=1)
        return "raw_frame", data

    def ingest_base64_payload(self, b64_str: str, sample_rate: int = 16000) -> bytes:
        """Decodes base64-encoded audio bytes from Agent 01 event envelopes."""
        try:
            pcm16 = base64.b64decode(b64_str)
        except Exception as exc:
            raise AudioValidationError(f"Base64 decoding failed: {exc}")

        self.validator.validate_pcm16(pcm16, sample_rate=sample_rate, channels=1)
        if sample_rate != 16000:
            pcm16 = resample_pcm16(pcm16, sample_rate, 16000)
        return pcm16

    def ingest_wav_file(self, wav_bytes: bytes, max_duration_sec: Optional[float] = None) -> Tuple[bytes, int, int]:
        """Ingests WAV/audio file bytes, normalizes to 16 kHz Mono PCM16, and validates duration."""
        pcm16, sr, channels = wav_bytes_to_pcm16(wav_bytes, target_sr=16000)
        limit = max_duration_sec if max_duration_sec is not None else 1800.0
        self.validator.validate_pcm16(pcm16, sample_rate=16000, channels=1, max_duration_sec=limit)
        return pcm16, 16000, 1

