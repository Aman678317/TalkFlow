"""Deterministic Energy-based VAD with adaptive noise floor tracking."""
from __future__ import annotations

import math
import numpy as np
from app.providers.vad.base import BaseVAD


class EnergyVAD(BaseVAD):
    """Energy-based VAD using RMS and continuous noise floor tracking."""

    def __init__(self, threshold_db: float = -38.0, adaptive: bool = True):
        self.threshold = 10 ** (threshold_db / 20.0)
        self.adaptive = adaptive
        self._noise_floor = self.threshold * 0.5
        self.reset()

    @property
    def name(self) -> str:
        return "energy"

    def is_available(self) -> bool:
        return True

    def reset(self) -> None:
        self._noise_floor = self.threshold * 0.5

    def get_noise_floor_rms(self) -> float:
        return self._noise_floor

    def process_chunk(self, pcm_bytes: bytes, sample_rate: int = 16000) -> float:
        if not pcm_bytes:
            return 0.0

        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if samples.size == 0:
            return 0.0

        rms = float(np.sqrt(np.mean(samples * samples)) + 1e-10)

        # Track noise floor on quieter frames
        if self.adaptive and rms < self._noise_floor * 4.0:
            self._noise_floor = 0.95 * self._noise_floor + 0.05 * rms

        gate = max(self.threshold, self._noise_floor * 2.5)
        if rms <= gate:
            return 0.0

        # Map excess dB over gate to probability [0.0, 1.0] over 20 dB dynamic range
        db_over = 20.0 * math.log10(rms / gate)
        return float(min(1.0, max(0.0, db_over / 20.0)))

