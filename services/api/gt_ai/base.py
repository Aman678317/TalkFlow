"""Provider base protocols (PDD §9.1).

Every concrete adapter implements one of these protocols. Business logic
depends ONLY on the protocols — never on a model library.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Protocol, runtime_checkable

from gt_ai.types import (
    AudioChunk,
    DetectionResult,
    TranslationRequest,
    TranslationResult,
    TranscriptChunk,
)


class BaseProvider(ABC):
    """Common lifecycle for all providers."""

    name: str = "base"
    task: str = "base"
    #: True when the provider is a local/self-hosted inference path.
    private: bool = True
    #: Relative quality tier used by the router (0..100).
    quality_tier: int = 50
    #: Relative cost tier used by the router (0..100, higher = more expensive).
    cost_tier: int = 50
    #: Typical latency class: "realtime" | "fast" | "batch"
    latency_class: str = "fast"
    #: True when a GPU is required/recommended.
    requires_gpu: bool = False

    async def warmup(self) -> None:  # pragma: no cover - default no-op
        """Pre-load models (model warm pool)."""

    async def healthcheck(self) -> bool:
        return True


@runtime_checkable
class TranslationProvider(Protocol):
    async def translate(self, req: TranslationRequest) -> TranslationResult: ...

    async def translate_stream(
        self, req: TranslationRequest
    ) -> AsyncIterator[str]:
        """Incremental translation output (token/segment stream)."""
        ...


@runtime_checkable
class STTProvider(Protocol):
    async def transcribe(
        self, audio: bytes, sample_rate: int, lang_hint: str | None = None
    ) -> TranscriptChunk: ...

    async def transcribe_stream(
        self, audio_chunks: AsyncIterator[bytes], sample_rate: int, lang_hint: str | None = None
    ) -> AsyncIterator[TranscriptChunk]: ...


@runtime_checkable
class TTSProvider(Protocol):
    async def synthesize(
        self, text: str, lang: str, voice: str | None = None
    ) -> AudioChunk: ...

    async def synthesize_stream(
        self, text: str, lang: str, voice: str | None = None
    ) -> AsyncIterator[AudioChunk]: ...


@runtime_checkable
class LanguageDetectionProvider(Protocol):
    async def detect(self, text: str) -> DetectionResult: ...


@runtime_checkable
class SummarizationProvider(Protocol):
    async def summarize(
        self, text: str, instruction: str = "", max_length: int = 400, lang: str = "en"
    ) -> str: ...

    async def extract_structured(
        self, text: str, schema_hint: str = "", lang: str = "en"
    ) -> dict: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
