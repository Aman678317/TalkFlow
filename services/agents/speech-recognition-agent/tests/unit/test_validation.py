"""Unit tests for AudioValidator."""
import pytest
from app.audio.validation import AudioValidator
from app.core.exceptions import AudioValidationError


def test_valid_pcm16():
    validator = AudioValidator()
    valid_pcm = b"\x00\x00" * 800  # 800 samples = 50ms at 16kHz
    validator.validate_pcm16(valid_pcm, sample_rate=16000, channels=1)


def test_empty_audio_raises():
    validator = AudioValidator()
    with pytest.raises(AudioValidationError, match="empty"):
        validator.validate_pcm16(b"", sample_rate=16000)


def test_unsupported_sample_rate():
    validator = AudioValidator()
    valid_pcm = b"\x00\x00" * 800
    with pytest.raises(AudioValidationError, match="Unsupported sample rate"):
        validator.validate_pcm16(valid_pcm, sample_rate=12345)


def test_misaligned_pcm_bytes():
    validator = AudioValidator()
    odd_bytes = b"\x00" * 15  # Not a multiple of 2
    with pytest.raises(AudioValidationError, match="aligned"):
        validator.validate_pcm16(odd_bytes, sample_rate=16000)


def test_oversized_audio_duration():
    validator = AudioValidator(max_duration_sec=2.0)
    oversized = b"\x00\x00" * int(16000 * 3.0)  # 3 seconds
    with pytest.raises(AudioValidationError, match="exceeds maximum"):
        validator.validate_pcm16(oversized, sample_rate=16000)

