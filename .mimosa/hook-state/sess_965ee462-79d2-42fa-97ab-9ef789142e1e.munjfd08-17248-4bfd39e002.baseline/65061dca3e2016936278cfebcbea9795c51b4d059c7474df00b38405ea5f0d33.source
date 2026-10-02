"""Core AI value types shared by every provider adapter.

These are deliberately small dataclasses (not Pydantic) so the AI layer has
zero web-framework dependencies and can run inside any worker.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Task(StrEnum):
    STT = "stt"
    MT = "mt"
    TTS = "tts"
    LANG_DETECT = "lang_detect"
    SUMMARIZE = "summarize"
    EMBED = "embed"


class Intent(StrEnum):
    LATENCY_OPTIMIZED = "latency_optimized"
    QUALITY_OPTIMIZED = "quality_optimized"
    COST_OPTIMIZED = "cost_optimized"
    PRIVATE_ONLY = "private_only"


@dataclass(slots=True)
class TranslationRequest:
    text: str
    source_lang: str          # ISO code or "auto"
    target_lang: str
    domain: str = "general"
    intent: Intent = Intent.QUALITY_OPTIMIZED
    context: list[str] = field(default_factory=list)
    glossary: dict[str, str] | None = None       # source term -> preferred target term
    style: dict[str, Any] | None = None          # style profile config
    tenant_private_only: bool = False


@dataclass(slots=True)
class TranslationResult:
    text: str
    source_lang: str
    target_lang: str
    model: str
    provider: str
    latency_ms: float
    quality_flags: list[str] = field(default_factory=list)
    confidence: float | None = None
    alternatives: list[str] = field(default_factory=list)

    @property
    def is_dev(self) -> bool:
        return "dev_provider" in self.quality_flags


@dataclass(slots=True)
class TranscriptChunk:
    text: str
    language: str | None
    is_final: bool
    start_ms: int = 0
    end_ms: int = 0
    confidence: float | None = None
    model: str = ""
    provider: str = ""


@dataclass(slots=True)
class AudioChunk:
    """PCM audio chunk. sample_rate/mono 16-bit signed LE unless stated."""
    data: bytes
    sample_rate: int = 24000
    encoding: str = "pcm_s16le"
    format: str = "wav"        # wav | pcm_s16le | mp3
    provider: str = ""
    model: str = ""
    duration_ms: float = 0.0
    is_dev: bool = False


@dataclass(slots=True)
class DetectionResult:
    language: str
    confidence: float
    provider: str
    alternatives: list[tuple[str, float]] = field(default_factory=list)


@dataclass(slots=True)
class RouteDecision:
    provider: str
    model: str
    task: Task
    reason: str
    latency_budget_ms: float | None = None
    started_at: float = field(default_factory=time.time)


@dataclass(slots=True)
class ProviderHealth:
    """Rolling health tracked by the router for adaptive selection."""
    ewma_latency_ms: float = 0.0
    error_count: int = 0
    request_count: int = 0
    available: bool = True
    gpu: bool = False

    @property
    def error_rate(self) -> float:
        return self.error_count / max(1, self.request_count)


class ProviderUnavailable(RuntimeError):
    """Raised when a provider cannot serve (missing model, crashed, etc.)."""


class UnsupportedLanguagePair(ValueError):
    """Raised when the capability registry forbids a pair."""
