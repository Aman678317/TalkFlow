"""Unit tests for sample rate conversion, channels downmixing, and float normalization."""
import numpy as np
from app.audio.normalization import AudioNormalizer
from tests.fixtures.audio_fixtures import generate_sine_wave


def test_float32_pcm16_roundtrip():
    normalizer = AudioNormalizer()
    orig_pcm = generate_sine_wave(freq_hz=440, duration_ms=100, sample_rate=16000)
    float_arr = normalizer.pcm16_to_float32(orig_pcm)
    assert float_arr.dtype == np.float32
    assert -1.0 <= np.min(float_arr)
    assert np.max(float_arr) <= 1.0

    roundtrip_pcm = normalizer.float32_to_pcm16(float_arr)
    assert len(roundtrip_pcm) == len(orig_pcm)


def test_sample_rate_conversion_48k_to_16k():
    normalizer = AudioNormalizer(target_sample_rate=16000, target_channels=1)
    # 100ms of 48kHz audio = 4800 samples = 9600 bytes
    pcm_48k = generate_sine_wave(freq_hz=440, duration_ms=100, sample_rate=48000)
    assert len(pcm_48k) == 4800 * 2

    pcm_16k = normalizer.normalize(pcm_48k, source_sample_rate=48000, source_channels=1)
    # 100ms of 16kHz audio = 1600 samples = 3200 bytes
    assert len(pcm_16k) == 1600 * 2


def test_sample_rate_conversion_8k_to_16k():
    normalizer = AudioNormalizer(target_sample_rate=16000, target_channels=1)
    # 100ms of 8kHz audio = 800 samples = 1600 bytes
    pcm_8k = generate_sine_wave(freq_hz=440, duration_ms=100, sample_rate=8000)
    assert len(pcm_8k) == 800 * 2

    pcm_16k = normalizer.normalize(pcm_8k, source_sample_rate=8000, source_channels=1)
    assert len(pcm_16k) == 1600 * 2


def test_stereo_to_mono_downmixing():
    normalizer = AudioNormalizer(target_sample_rate=16000, target_channels=1)
    # Generate 100ms stereo 16kHz: 1600 samples * 2 channels = 3200 samples = 6400 bytes
    left = np.frombuffer(generate_sine_wave(freq_hz=400, duration_ms=100, sample_rate=16000), dtype=np.int16)
    right = np.frombuffer(generate_sine_wave(freq_hz=800, duration_ms=100, sample_rate=16000), dtype=np.int16)
    stereo = np.column_stack((left, right)).flatten().tobytes()
    assert len(stereo) == 6400

    mono = normalizer.normalize(stereo, source_sample_rate=16000, source_channels=2)
    # Target mono 100ms = 1600 samples = 3200 bytes
    assert len(mono) == 3200

