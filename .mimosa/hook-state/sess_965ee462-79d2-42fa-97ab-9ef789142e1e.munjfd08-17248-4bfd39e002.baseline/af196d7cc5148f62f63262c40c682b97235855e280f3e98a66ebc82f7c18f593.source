"""VAD providers.

- EnergyVAD: deterministic RMS + adaptive noise floor (real DSP, always available).
- SileroVAD: silero-vad ONNX model when downloaded (Phase-2 upgrade; same interface).

Both emit speech probability per chunk; the realtime pipeline turns probabilities into
speech_started / speech_ended events with hangover, per section 100.
"""
from __future__ import annotations

import math

import numpy as np


class EnergyVAD:
    name = "energy"

    def __init__(self, threshold_db: float = -38.0, adaptive: bool = True):
        self.threshold = 10 ** (threshold_db / 20)
        self.adaptive = adaptive
        self._noise_floor = self.threshold * 0.5
        self.reset()

    def healthy(self) -> bool:
        return True

    def reset(self) -> None:
        self._noise_floor = self.threshold * 0.5

    def process_chunk(self, pcm16: bytes, sample_rate: int = 16000) -> float:
        if not pcm16:
            return 0.0
        x = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(x * x)) + 1e-10)
        if self.adaptive:
            # slow noise-floor tracking on quiet frames
            if rms < self._noise_floor * 4:
                self._noise_floor = 0.95 * self._noise_floor + 0.05 * rms
        gate = max(self.threshold, self._noise_floor * 3)
        if rms <= gate:
            return 0.0
        # squash to probability-like 0..1 (log scale, 20 dB dynamic window)
        db_over = 20 * math.log10(rms / gate)
        return float(min(1.0, db_over / 20.0))


class SileroVAD:
    name = "silero"

    def __init__(self):
        self._model = None
        self._failed = False

    def _ensure(self):
        if self._failed:
            return False
        if self._model is None:
            try:
                import torch
                self._model = torch.hub.load(repo_or_dir="snakers4/silero-vad",
                                             model="silero_vad", trust_repo=True)
            except Exception:
                self._failed = True
                return False
        return True

    def healthy(self) -> bool:
        return self._ensure()

    def reset(self) -> None:
        if self._ensure():
            self._model[0].reset_states()

    def process_chunk(self, pcm16: bytes, sample_rate: int = 16000) -> float:
        if not self._ensure():
            raise RuntimeError("silero unavailable")
        import torch
        x = torch.from_numpy(np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0)
        with torch.no_grad():
            prob = float(self._model[0](x, sample_rate).item())
        return prob


def get_vad(provider: str):
    if provider == "silero":
        v = SileroVAD()
        if v.healthy():
            return v
    return EnergyVAD()
