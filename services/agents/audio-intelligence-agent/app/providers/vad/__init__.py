"""VAD provider factory."""
from __future__ import annotations

from typing import Optional
from app.providers.vad.base import BaseVAD
from app.providers.vad.energy import EnergyVAD
from app.providers.vad.silero import SileroVAD
from app.providers.vad.webrtc import WebRTCVAD


def get_vad_provider(
    name: str = "silero",
    sensitivity: int = 2,
    model_path: Optional[str] = None,
) -> BaseVAD:
    """Instantiates requested VAD provider with fallback to EnergyVAD on failure."""
    req = name.lower().strip()

    if req == "silero":
        silero = SileroVAD(model_path=model_path)
        if silero.is_available():
            return silero
        # Graceful fallback to WebRTC or Energy
        webrtc = WebRTCVAD(mode=sensitivity)
        if webrtc.is_available():
            return webrtc
        return EnergyVAD()

    elif req == "webrtc":
        webrtc = WebRTCVAD(mode=sensitivity)
        if webrtc.is_available():
            return webrtc
        return EnergyVAD()

    return EnergyVAD()


__all__ = ["BaseVAD", "EnergyVAD", "SileroVAD", "WebRTCVAD", "get_vad_provider"]

