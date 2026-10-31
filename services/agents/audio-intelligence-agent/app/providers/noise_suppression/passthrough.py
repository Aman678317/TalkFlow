"""Passthrough noise suppressor for benchmarking, debugging, and transparent bypass."""
from __future__ import annotations

from app.providers.noise_suppression.base import BaseNoiseSuppressor


class PassthroughNoiseSuppressor(BaseNoiseSuppressor):
    """Zero-op suppressor that preserves pristine original PCM frames without modification."""

    @property
    def name(self) -> str:
        return "passthrough"

    def is_available(self) -> bool:
        return True

    def reset(self) -> None:
        pass

    def process_frame(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 16000,
        is_speech: bool = False,
    ) -> bytes:
        return pcm_bytes

