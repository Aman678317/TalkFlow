"""Noise suppression provider factory."""
from __future__ import annotations

from app.providers.noise_suppression.base import BaseNoiseSuppressor
from app.providers.noise_suppression.noisereduce_provider import NoisereduceSuppressor
from app.providers.noise_suppression.passthrough import PassthroughNoiseSuppressor
from app.providers.noise_suppression.spectral import SpectralNoiseSuppressor


def get_noise_suppressor(
    name: str = "spectral",
    enabled: bool = True,
) -> BaseNoiseSuppressor:
    """Instantiates requested noise suppression provider with fallback to passthrough."""
    if not enabled:
        return PassthroughNoiseSuppressor()

    req = name.lower().strip()
    if req == "spectral":
        return SpectralNoiseSuppressor()
    elif req == "noisereduce":
        nr_sup = NoisereduceSuppressor()
        if nr_sup.is_available():
            return nr_sup
        return SpectralNoiseSuppressor()
    return PassthroughNoiseSuppressor()


__all__ = [
    "BaseNoiseSuppressor",
    "SpectralNoiseSuppressor",
    "NoisereduceSuppressor",
    "PassthroughNoiseSuppressor",
    "get_noise_suppressor",
]

