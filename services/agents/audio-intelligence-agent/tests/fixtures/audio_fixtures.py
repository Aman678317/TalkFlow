"""Synthetic test signal generator producing deterministic, reproducible audio fixtures."""
from __future__ import annotations

import io
import math
import numpy as np
import soundfile as sf


def generate_silence(duration_ms: int = 1000, sample_rate: int = 16000) -> bytes:
    """Generates pure digital silence PCM16 bytes."""
    num_samples = int(sample_rate * (duration_ms / 1000.0))
    return (np.zeros(num_samples, dtype=np.int16)).tobytes()


def generate_sine_wave(
    freq_hz: float = 440.0,
    duration_ms: int = 1000,
    sample_rate: int = 16000,
    amplitude: float = 0.5,
) -> bytes:
    """Generates pure sinusoidal tone PCM16 bytes."""
    num_samples = int(sample_rate * (duration_ms / 1000.0))
    t = np.linspace(0, duration_ms / 1000.0, num_samples, endpoint=False)
    waveform = amplitude * np.sin(2 * np.pi * freq_hz * t)
    clipped = np.clip(waveform, -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16).tobytes()


def generate_white_noise(
    duration_ms: int = 1000,
    sample_rate: int = 16000,
    amplitude: float = 0.1,
    seed: int = 42,
) -> bytes:
    """Generates reproducible Gaussian white noise PCM16 bytes."""
    rng = np.random.default_rng(seed)
    num_samples = int(sample_rate * (duration_ms / 1000.0))
    noise = rng.normal(0, amplitude, num_samples)
    clipped = np.clip(noise, -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16).tobytes()


def generate_speech_like_signal(
    duration_ms: int = 1000,
    sample_rate: int = 16000,
    amplitude: float = 0.6,
    seed: int = 42,
) -> bytes:
    """Generates synthetic harmonic voice-like signal simulating speech formants and syllable pauses."""
    num_samples = int(sample_rate * (duration_ms / 1000.0))
    t = np.linspace(0, duration_ms / 1000.0, num_samples, endpoint=False)

    # Fundamental voice frequencies (f0, f1, f2 formants)
    f0 = 150.0   # Pitch fundamental
    f1 = 700.0   # First formant
    f2 = 1800.0  # Second formant
    f3 = 2800.0  # Third formant

    voice = (
        0.5 * np.sin(2 * np.pi * f0 * t)
        + 0.3 * np.sin(2 * np.pi * f1 * t)
        + 0.15 * np.sin(2 * np.pi * f2 * t)
        + 0.05 * np.sin(2 * np.pi * f3 * t)
    )

    # Syllabic envelope modulation (approx 4 syllables per second ~ 4 Hz modulation)
    syllables = 0.5 * (1.0 + np.sin(2 * np.pi * 4.0 * t - np.pi / 2))
    modulated = amplitude * voice * syllables

    clipped = np.clip(modulated, -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16).tobytes()


def generate_clipped_signal(
    duration_ms: int = 1000,
    sample_rate: int = 16000,
    amplitude: float = 2.0,
) -> bytes:
    """Generates heavily overdriven clipped audio."""
    num_samples = int(sample_rate * (duration_ms / 1000.0))
    t = np.linspace(0, duration_ms / 1000.0, num_samples, endpoint=False)
    waveform = amplitude * np.sin(2 * np.pi * 300.0 * t)
    clipped = np.clip(waveform, -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16).tobytes()


def generate_noisy_speech(
    duration_ms: int = 1000,
    sample_rate: int = 16000,
    snr_db: float = 10.0,
    seed: int = 42,
) -> bytes:
    """Mixes speech-like signal with noise at specified SNR."""
    speech_pcm = generate_speech_like_signal(duration_ms, sample_rate, amplitude=0.5, seed=seed)
    speech_float = np.frombuffer(speech_pcm, dtype=np.int16).astype(np.float32) / 32768.0

    speech_power = np.mean(speech_float**2) + 1e-10
    noise_power_target = speech_power / (10 ** (snr_db / 10.0))
    noise_std = np.sqrt(noise_power_target)

    rng = np.random.default_rng(seed)
    noise = rng.normal(0, noise_std, len(speech_float))
    mixed = speech_float + noise
    clipped = np.clip(mixed, -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16).tobytes()


def pcm_to_wav_bytes(pcm_bytes: bytes, sample_rate: int = 16000, channels: int = 1) -> bytes:
    """Wraps raw PCM16 bytes in a RIFF/WAV container."""
    samples = np.frombuffer(pcm_bytes, dtype=np.int16)
    out_buf = io.BytesIO()
    with sf.SoundFile(
        out_buf,
        mode="w",
        format="WAV",
        samplerate=sample_rate,
        channels=channels,
        subtype="PCM_16",
    ) as f:
        f.write(samples)
    return out_buf.getvalue()

