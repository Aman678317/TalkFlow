"""AI provider interfaces. Business logic depends ONLY on these — never on a concrete model.

Application → AI abstraction → provider adapter → actual model.
Every provider reports its identity (provider/model/version) so routes are auditable,
and raises ProviderUnavailable so the fallback chain can take over.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Protocol, runtime_checkable


class ProviderUnavailable(Exception):
    """Raised when a provider cannot serve (not installed, unhealthy, unsupported pair)."""

    def __init__(self, provider: str, reason: str):
        super().__init__(f"{provider}: {reason}")
        self.provider = provider
        self.reason = reason


@dataclass
class STTResult:
    text: str
    language: str            # detected or forced language (ISO code)
    language_probability: float = 0.0
    confidence: float = 0.0
    provider: str = ""
    model: str = ""
    duration_ms: float = 0.0
    segments: list[dict] = field(default_factory=list)


@dataclass
class TranslationResult:
    text: str
    source_language: str
    target_language: str
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    confidence: float = 0.0
    quality_flags: list[str] = field(default_factory=list)
    pivoted: bool = False    # true if the provider used a pivot language (must be policy-allowed)


@dataclass
class TTSResult:
    audio: bytes             # WAV/PCM container bytes
    sample_rate: int
    provider: str = ""
    model: str = ""
    voice: str = ""
    latency_ms: float = 0.0
    synthetic: bool = True   # AI voice safety: synthetic output is always identifiable


@dataclass
class DetectionResult:
    language: str
    confidence: float
    provider: str = ""
    alternatives: list[tuple[str, float]] = field(default_factory=list)


@dataclass
class VADSegment:
    start_ms: int
    end_ms: int
    probability: float = 1.0


@runtime_checkable
class STTProvider(Protocol):
    name: str

    def healthy(self) -> bool: ...
    def supported_languages(self) -> set[str]: ...
    def transcribe(self, audio_pcm16: bytes, sample_rate: int, *,
                   language: str | None = None, task: str = "transcribe") -> STTResult: ...


@runtime_checkable
class StreamingSTTProvider(STTProvider, Protocol):
    def transcribe_stream(self, chunks: Iterator[bytes], sample_rate: int, *,
                          language: str | None = None) -> Iterator[STTResult]: ...


@runtime_checkable
class TranslationProvider(Protocol):
    name: str

    def healthy(self) -> bool: ...
    def supported_pairs(self) -> set[tuple[str, str]]: ...
    def translate(self, text: str, source_language: str, target_language: str, *,
                  glossary: dict[str, str] | None = None, domain: str = "general",
                  style_hint: str = "") -> TranslationResult: ...


@runtime_checkable
class TTSProvider(Protocol):
    name: str

    def healthy(self) -> bool: ...
    def supported_languages(self) -> set[str]: ...
    def list_voices(self, language: str) -> list[str]: ...
    def synthesize(self, text: str, language: str, *, voice: str = "") -> TTSResult: ...


@runtime_checkable
class LanguageDetectionProvider(Protocol):
    name: str

    def healthy(self) -> bool: ...
    def detect(self, text: str) -> DetectionResult: ...


@runtime_checkable
class VADProvider(Protocol):
    name: str

    def healthy(self) -> bool: ...
    def process_chunk(self, pcm16: bytes, sample_rate: int) -> float: ...
    def reset(self) -> None: ...


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def healthy(self) -> bool: ...
    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 512,
                 temperature: float = 0.2) -> str: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str
    dim: int

    def healthy(self) -> bool: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class DocumentParserProvider(Protocol):
    name: str

    def healthy(self) -> bool: ...
    def parse(self, data: bytes, mime_type: str, filename: str) -> list[dict]:
        """Returns canonical document representation:
        [{kind, page, bbox?, text, translatable}] preserving layout/reading order."""
