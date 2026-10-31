"""Audio ducking mixer for concurrent original and translated playback."""
from __future__ import annotations

import math
from typing import Optional
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("transport.ducking")


class DuckingMixer:
    """Manages volume attenuation (ducking) of original human speech when translated audio plays."""

    def __init__(
        self,
        ducking_ratio: Optional[float] = None,
        attack_ms: Optional[float] = None,
        release_ms: Optional[float] = None,
    ):
        settings = get_settings()
        self.ducking_ratio = (
            ducking_ratio
            if ducking_ratio is not None
            else float(settings.audio_sync.ducking_ratio)
        )
        self.attack_ms = (
            attack_ms
            if attack_ms is not None
            else float(settings.audio_sync.ducking_attack_ms)
        )
        self.release_ms = (
            release_ms
            if release_ms is not None
            else float(settings.audio_sync.ducking_release_ms)
        )

    def get_gains_for_mode(self, playback_mode: str, is_translation_active: bool) -> dict[str, float]:
        """Compute gains for original audio and translated audio based on playback mode."""
        mode = playback_mode.lower()

        if mode == "muted":
            return {"original_gain": 0.0, "translated_gain": 0.0}

        if mode == "original":
            return {"original_gain": 1.0, "translated_gain": 0.0}

        if mode == "translated":
            return {"original_gain": 0.0, "translated_gain": 1.0}

        if mode == "both":
            if is_translation_active:
                return {
                    "original_gain": self.ducking_ratio,
                    "translated_gain": 1.0,
                }
            return {"original_gain": 1.0, "translated_gain": 0.0}

        # Default fallback
        return {"original_gain": 0.0, "translated_gain": 1.0}

    def calculate_attenuation_db(self, gain: float) -> float:
        """Convert linear gain to decibels (dB)."""
        if gain <= 0.0:
            return -100.0
        return 20.0 * math.log10(gain)

