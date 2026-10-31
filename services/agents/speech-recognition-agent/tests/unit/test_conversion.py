"""Unit tests for audio conversion utilities."""
import numpy as np
from app.audio.conversion import (
    float32_to_pcm16,
    pcm16_to_float32,
    pcm16_to_wav_bytes,
    resample_pcm16,
    wav_bytes_to_pcm16,
)
from tests.fixtures.audio_fixtures import generate_tone


def test_pcm16_float32_roundtrip():
    tone_pcm = generate_tone(440.0, 0.1, 16000)
    float_arr = pcm16_to_float32(tone_pcm)
    assert len(float_arr) == 1600
    assert -1.0 <= float_arr.max() <= 1.0
    assert -1.0 <= float_arr.min() <= 1.0

    recovered_pcm = float32_to_pcm16(float_arr)
    assert len(recovered_pcm) == len(tone_pcm)


def test_wav_container_roundtrip():
    tone_pcm = generate_tone(440.0, 0.2, 16000)
    wav_bytes = pcm16_to_wav_bytes(tone_pcm, sample_rate=16000, channels=1)
    assert wav_bytes.startswith(b"RIFF")

    recovered_pcm, sr, ch = wav_bytes_to_pcm16(wav_bytes)
    assert sr == 16000
    assert ch == 1
    assert recovered_pcm == tone_pcm


def test_resample_pcm16():
    tone_48k = generate_tone(440.0, 0.1, 48000)
    resampled_16k = resample_pcm16(tone_48k, orig_sr=48000, target_sr=16000)
    expected_samples = int(0.1 * 16000)
    assert len(resampled_16k) == expected_samples * 2

