"""Abstract base interface for noise suppression providers."""
from __future__ import annotations

from abc import ABC, abstractmethod


class BaseNoiseSuppressor(ABC):
    """Abstract interface for all noise suppression providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the noise suppression provider."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the provider is operational."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Resets running noise estimate and filter state."""
        pass

    @abstractmethod
    def process_frame(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 16000,
        is_speech: bool = False,
    ) -> bytes:
        """Applies noise suppression to a single PCM16 audio frame and returns cleaned PCM16 bytes."""
        pass

