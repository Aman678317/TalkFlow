"""Base interface for Agent 06 Text-to-Speech providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Optional
from pydantic import BaseModel, Field


class TTSChunk(BaseModel):
    """Audio chunk produced by a TTS provider."""
    data: bytes
    sample_rate: int = 24000
    encoding: str = "pcm_s16le"
    format: str = "wav"
    duration_ms: float = 0.0
    provider: str
    model: str
    voice: str
    is_dev: bool = False
    synthetic: bool = True
    chunk_index: int = 0
    is_last: bool = False


class TTSResult(BaseModel):
    """Complete synthesized audio result."""
    audio_data: bytes
    pcm_data: bytes
    sample_rate: int = 24000
    encoding: str = "pcm_s16le"
    format: str = "wav"
    duration_ms: float = 0.0
    provider: str
    model: str
    voice: str
    latency_ms: float = 0.0
    is_dev: bool = False
    synthetic: bool = True


class BaseTTSProvider(ABC):
    """Abstract base class for all TTS providers."""

    name: str
    is_local: bool
    supported_languages: List[str]

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice_id: str,
        language: str,
        sample_rate: int = 24000,
        **kwargs,
    ) -> TTSResult:
        """Synthesize entire text into TTSResult."""
        pass

    @abstractmethod
    async def synthesize_stream(
        self,
        text: str,
        voice_id: str,
        language: str,
        sample_rate: int = 24000,
        **kwargs,
    ) -> AsyncIterator[TTSChunk]:
        """Synthesize text as streaming sequence of TTSChunks."""
        pass

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Return True if the provider is loaded and ready."""
        pass

