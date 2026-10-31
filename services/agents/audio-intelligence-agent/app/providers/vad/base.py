"""Abstract base interface for Voice Activity Detection (VAD) providers."""
from __future__ import annotations

from abc import ABC, abstractmethod


class BaseVAD(ABC):
    """Abstract interface for all VAD providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name identifier of the VAD provider."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the provider model/backend is available and healthy."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Resets any internal RNN/temporal filter states for a new speaker/turn."""
        pass

    @abstractmethod
    def process_chunk(self, pcm_bytes: bytes, sample_rate: int = 16000) -> float:
        """Processes an audio chunk and returns speech probability in [0.0, 1.0]."""
        pass

