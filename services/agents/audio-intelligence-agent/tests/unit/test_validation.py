"""Unit tests for audio validation and sequence tracking."""
import pytest
from app.audio.validation import AudioValidator
from app.core.exceptions import (
    AudioValidationError,
    CorruptedFrameError,
    UnsupportedAudioFormatError,
)
from tests.fixtures.audio_fixtures import generate_silence


def test_valid_pcm16_input():
    validator = AudioValidator()
    valid_frame = generate_silence(duration_ms=50, sample_rate=16000)
    assert len(valid_frame) == 1600  # 50ms @ 16kHz int16 mono = 800 samples * 2
    assert validator.validate_frame(valid_frame, sample_rate=16000, channels=1, encoding="pcm_s16le") is True


def test_empty_audio_input():
    validator = AudioValidator()
    with pytest.raises(AudioValidationError, match="Audio frame is empty"):
        validator.validate_frame(b"", sample_rate=16000, channels=1)


def test_oversized_audio_frame():
    validator = AudioValidator(max_frame_size_bytes=4096)
    oversized = b"\x00" * 5000
    with pytest.raises(AudioValidationError, match="exceeds maximum allowable size"):
        validator.validate_frame(oversized)


def test_misaligned_frame_bytes():
    validator = AudioValidator()
    # 1599 bytes is odd; int16 mono requires multiples of 2 bytes
    misaligned = b"\x00" * 1599
    with pytest.raises(CorruptedFrameError, match="not aligned"):
        validator.validate_frame(misaligned, sample_rate=16000, channels=1)


def test_unsupported_sample_rate():
    validator = AudioValidator()
    valid_pcm = generate_silence(50, 16000)
    with pytest.raises(UnsupportedAudioFormatError, match="Unsupported sample rate"):
        validator.validate_frame(valid_pcm, sample_rate=11025)


def test_unsupported_encoding():
    validator = AudioValidator()
    valid_pcm = generate_silence(50, 16000)
    with pytest.raises(UnsupportedAudioFormatError, match="Unsupported audio encoding"):
        validator.validate_frame(valid_pcm, encoding="flac")


def test_sequence_ordering_and_monotonicity():
    validator = AudioValidator()

    # Initial frame
    valid, status = validator.validate_sequence(current_seq=0, last_seq=-1)
    assert valid is True
    assert status == "initial"

    # Monotonic next frame
    valid, status = validator.validate_sequence(current_seq=1, last_seq=0)
    assert valid is True
    assert status == "valid"

    # Duplicate sequence
    valid, status = validator.validate_sequence(current_seq=1, last_seq=1)
    assert valid is False
    assert status == "duplicate"

    # Out of order sequence
    valid, status = validator.validate_sequence(current_seq=0, last_seq=2)
    assert valid is False
    assert status == "out_of_order"

    # Gap detected
    valid, status = validator.validate_sequence(current_seq=5, last_seq=2)
    assert valid is True
    assert "gap_detected" in status

