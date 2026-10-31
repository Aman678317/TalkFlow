"""Synthetic test audio fixtures for deterministic STT testing."""
from __future__ import annotations

import io
import wave
import numpy as np


def generate_silence(duration_sec: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Generates pure silence PCM16 bytes."""
    num_samples = int(duration_sec * sample_rate)
    return np.zeros(num_samples, dtype=np.int16).tobytes()


def generate_tone(frequency: float = 440.0, duration_sec: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Generates pure sine wave PCM16 bytes."""
    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), endpoint=False)
    samples = (np.sin(2 * np.pi * frequency * t) * 16384).astype(np.int16)
    return samples.tobytes()


def wrap_pcm16_in_wav(pcm16_bytes: bytes, sample_rate: int = 16000, channels: int = 1) -> bytes:
    """Wraps raw PCM16 bytes in a standard RIFF/WAV header."""
    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16_bytes)
    return bio.getvalue()

