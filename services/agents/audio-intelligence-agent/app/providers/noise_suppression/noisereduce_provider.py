"""noisereduce package wrapper for stationary and non-stationary noise suppression."""
from __future__ import annotations

import numpy as np
from app.providers.noise_suppression.base import BaseNoiseSuppressor

try:
    import noisereduce as nr
except ImportError:
    nr = None  # type: ignore


class NoisereduceSuppressor(BaseNoiseSuppressor):
    """Wrapper around the noisereduce library using spectral gating."""

    def __init__(self, prop_decrease: float = 0.8):
        self.prop_decrease = prop_decrease
        self._noise_profile: np.ndarray | None = None

    @property
    def name(self) -> str:
        return "noisereduce"

    def is_available(self) -> bool:
        return nr is not None

    def reset(self) -> None:
        self._noise_profile = None

    def process_frame(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 16000,
        is_speech: bool = False,
    ) -> bytes:
        if not self.is_available() or not pcm_bytes:
            return pcm_bytes

        audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if len(audio) < 128:
            return pcm_bytes

        try:
            if not is_speech:
                self._noise_profile = audio.copy()

            if self._noise_profile is not None and len(self._noise_profile) >= 128:
                reduced = nr.reduce_noise(
                    y=audio,
                    sr=sample_rate,
                    y_noise=self._noise_profile,
                    prop_decrease=self.prop_decrease,
                    stationary=True,
                )
            else:
                reduced = nr.reduce_noise(
                    y=audio,
                    sr=sample_rate,
                    prop_decrease=self.prop_decrease,
                    stationary=True,
                )

            clipped = np.clip(reduced, -1.0, 1.0)
            return (clipped * 32767.0).astype(np.int16).tobytes()
        except Exception:
            # Honest degradation: return unmodified audio on filter failure
            return pcm_bytes

