"""Unit tests for noise suppression providers."""
import numpy as np
from app.providers.noise_suppression.noisereduce_provider import NoisereduceSuppressor
from app.providers.noise_suppression.passthrough import PassthroughNoiseSuppressor
from app.providers.noise_suppression.spectral import SpectralNoiseSuppressor
from tests.fixtures.audio_fixtures import (
    generate_noisy_speech,
    generate_white_noise,
)


def test_passthrough_preserves_audio_bytes():
    suppressor = PassthroughNoiseSuppressor()
    raw = generate_white_noise(duration_ms=100, sample_rate=16000)
    out = suppressor.process_frame(raw, 16000, is_speech=False)
    assert out == raw


def test_spectral_noise_suppression_reduces_noise_energy():
    suppressor = SpectralNoiseSuppressor()
    # Feed noise frames to establish noise PSD
    noise_frame = generate_white_noise(duration_ms=50, sample_rate=16000, amplitude=0.2)
    for _ in range(8):
        suppressor.process_frame(noise_frame, 16000, is_speech=False)

    # Process another noise frame
    cleaned_noise = suppressor.process_frame(noise_frame, 16000, is_speech=False)

    orig_arr = np.frombuffer(noise_frame, dtype=np.int16).astype(np.float32) / 32768.0
    cleaned_arr = np.frombuffer(cleaned_noise, dtype=np.int16).astype(np.float32) / 32768.0

    orig_energy = np.mean(orig_arr**2)
    cleaned_energy = np.mean(cleaned_arr**2)

    assert cleaned_energy < orig_energy


def test_noisereduce_provider():
    suppressor = NoisereduceSuppressor()
    if not suppressor.is_available():
        return

    noisy_speech = generate_noisy_speech(duration_ms=100, sample_rate=16000, snr_db=5.0)
    cleaned = suppressor.process_frame(noisy_speech, 16000, is_speech=True)
    assert len(cleaned) == len(noisy_speech)

