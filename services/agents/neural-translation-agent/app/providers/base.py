"""Base provider abstraction and data models matching canonical TalkFlow contract."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, AsyncIterator, Dict, List, Optional, Protocol, runtime_checkable


class Intent(StrEnum):
    LATENCY_OPTIMIZED = "latency_optimized"
    QUALITY_OPTIMIZED = "quality_optimized"
    COST_OPTIMIZED = "cost_optimized"
    PRIVATE_ONLY = "private_only"
    OFFLINE_ONLY = "offline_only"
    EXPERIMENTAL = "experimental"


@dataclass(slots=True)
class TranslationRequest:
    """Canonical translation request object."""
    text: str
    source_lang: str
    target_lang: str
    domain: str = "general"
    intent: Intent = Intent.QUALITY_OPTIMIZED
    context: List[str] = field(default_factory=list)
    glossary: Optional[Dict[str, str]] = None
    style: Optional[Dict[str, Any]] = None
    tenant_private_only: bool = False
    session_id: Optional[str] = None
    speaker_id: Optional[str] = None
    segment_id: Optional[str] = None


@dataclass(slots=True)
class TranslationResult:
    """Canonical translation result object."""
    text: str
    source_lang: str
    target_lang: str
    model: str
    provider: str
    latency_ms: float
    quality_flags: List[str] = field(default_factory=list)
    confidence: Optional[float] = None
    alternatives: List[str] = field(default_factory=list)
    tm_match: Optional[str] = None
    glossary_applied: bool = False
    pivoted: bool = False
    source_equals_target: bool = False


class BaseProvider(ABC):
    """Lifecycle and telemetry metadata for translation providers."""

    name: str = "base"
    task: str = "mt"
    private: bool = True
    quality_tier: int = 50
    cost_tier: int = 50
    latency_class: str = "fast"
    requires_gpu: bool = False

    async def warmup(self) -> None:
        """Pre-load weights or packages into memory."""

    async def healthcheck(self) -> bool:
        """Returns True if the provider is currently ready to serve inference."""
        return True

    def runtime_ready(self) -> bool:
        """Cheap synchronous pre-flight check before entering routing chain."""
        return True

    @abstractmethod
    async def translate(self, req: TranslationRequest) -> TranslationResult:
        """Translates text from req.source_lang to req.target_lang."""

    async def translate_stream(self, req: TranslationRequest) -> AsyncIterator[str]:
        """Optional incremental token streaming for supported backends."""
        result = await self.translate(req)
        yield result.text


@runtime_checkable
class TranslationProvider(Protocol):
    """Runtime checkable protocol matching TalkFlow gt_ai.base."""
    async def translate(self, req: TranslationRequest) -> TranslationResult: ...
    async def translate_stream(self, req: TranslationRequest) -> AsyncIterator[str]: ...

