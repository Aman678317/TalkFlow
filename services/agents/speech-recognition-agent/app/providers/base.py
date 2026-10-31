"""Base STT provider protocol and abstract class compatible with TalkFlow."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Set, Tuple
from app.models.schemas import STTResult


class STTProvider(ABC):
    """Abstract base class for all speech-to-text recognition providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g. 'faster-whisper', 'whisper-onnx')."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Loaded model size or identifier (e.g. 'base', 'small', 'tiny')."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Fast non-blocking probe checking if provider weights/dependencies are present."""
        ...

    @abstractmethod
    def is_healthy(self) -> bool:
        """Reports runtime health of the provider."""
        ...

    @abstractmethod
    def supported_languages(self) -> Set[str]:
        """Returns set of ISO language codes supported by this provider."""
        ...

    @abstractmethod
    def transcribe(
        self,
        audio_pcm16: bytes,
        sample_rate: int = 16000,
        *,
        language_hint: Optional[str] = None,
        word_timestamps: bool = True,
    ) -> STTResult:
        """Transcribes PCM16 audio bytes and returns structured STTResult."""
        ...

    @abstractmethod
    def detect_language(
        self,
        audio_pcm16: bytes,
        sample_rate: int = 16000,
    ) -> Tuple[str, float]:
        """Detects spoken language from audio frames, returning (language_code, probability)."""
        ...

