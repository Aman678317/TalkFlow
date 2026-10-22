"""Shared domain types for the GlobalTalk AI SDK and server.

These dataclasses are the *only* types that cross the boundary between
the business logic layer and the AI/translation layer.  Never pass raw dicts.

Design rule: **no FastAPI / Pydantic / SQLAlchemy imports here**.
This module must be importable in any context — server, CLI, tests, notebooks.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Intent(str, Enum):
    """Translation routing intent — controls model selection in the model router."""
    QUALITY_OPTIMIZED = "quality_optimized"   # best accuracy, slower
    LATENCY_OPTIMIZED = "latency_optimized"   # fastest, slightly lower quality
    OFFLINE_ONLY      = "offline_only"        # no network calls; CPU-only models
    COST_OPTIMIZED    = "cost_optimized"      # smallest model that passes QA gates


class Formality(str, Enum):
    DEFAULT = "default"
    MORE    = "more"    # formal
    LESS    = "less"    # informal


class DocumentStatus(str, Enum):
    QUEUED     = "queued"
    PROCESSING = "processing"
    DONE       = "done"
    ERROR      = "error"


# ---------------------------------------------------------------------------
# Request / Result types
# ---------------------------------------------------------------------------

@dataclass
class TranslationRequest:
    """Input to the translation pipeline (all fields optional beyond text+target)."""
    text: str
    target_lang: str
    source_lang: str = "AUTO"
    formality: Formality = Formality.DEFAULT
    intent: Intent = Intent.QUALITY_OPTIMIZED
    glossary_id: str | None = None
    style_profile_id: str | None = None
    tm_id: str | None = None
    context_str: str | None = None
    preserve_formatting: bool = True
    tag_handling: str = "off"     # "off" | "xml" | "html"
    product: str = "text"         # text | document | realtime | chat


@dataclass
class TranslationResult:
    """Output from the translation pipeline."""
    translated_text: str
    detected_source_lang: str
    target_lang: str
    model_used: str = ""
    model_version: str = ""
    tm_hit: bool = False
    tm_source: str = ""           # "exact" | "fuzzy" | "semantic" | ""
    quality_score: float = 0.0    # 0..1; BLEU-derived or heuristic
    character_count: int = 0
    latency_ms: float = 0.0
    passed_qa: bool = True
    qa_warnings: list[str] = field(default_factory=list)


@dataclass
class WriteRequest:
    """Input to the writing assistant."""
    text: str
    style: str = "business"       # business | academic | casual | simple | creative
    tone: str  = "professional"   # professional | friendly | confident | diplomatic | direct
    lang: str  = "en"
    preserve_proper_nouns: bool = True


@dataclass
class WriteDiff:
    """A single tracked change from the writing assistant."""
    start: int
    end: int
    original: str
    replacement: str
    change_type: str   # grammar | style | vocabulary | tone | spelling
    explanation: str


@dataclass
class WriteResult:
    """Output from the writing assistant."""
    text: str                              # final rewritten text
    original: str                          # original input
    changes_count: int = 0
    diffs: list[WriteDiff] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    style: str = ""
    tone: str = ""


@dataclass
class DocumentJob:
    """Tracks an async document translation job."""
    id: str
    status: DocumentStatus
    filename: str = ""
    source_lang: str = ""
    target_lang: str = ""
    error: str = ""
    progress: float = 0.0   # 0..1
    download_url: str = ""


@dataclass
class VoiceSession:
    """Returned when a realtime voice session is created."""
    session_id: str
    websocket_url: str
    source_lang: str
    target_langs: list[str]
    speaker_id: str = ""
    reconnect_token: str = ""


@dataclass
class LanguageInfo:
    """A language supported by GlobalTalk AI."""
    language: str          # BCP-47 code e.g. "EN", "HI", "JA"
    name: str              # Human-readable e.g. "English"
    supports_formality: bool = False
    supports_write: bool = False
    supports_voice: bool = False
    voice_engine: str = ""   # e.g. "kokoro", "piper", ""


@dataclass
class UsageSummary:
    """Current usage and quota for an organization."""
    character_count: int
    character_limit: int
    stt_seconds: int = 0
    stt_limit_seconds: int = 0
    tts_seconds: int = 0
    tts_limit_seconds: int = 0

    @property
    def characters_remaining(self) -> int:
        return max(0, self.character_limit - self.character_count)

    @property
    def quota_fraction_used(self) -> float:
        if self.character_limit == 0:
            return 0.0
        return self.character_count / self.character_limit


# ---------------------------------------------------------------------------
# Internal AI provider types (used by model_router and providers)
# ---------------------------------------------------------------------------

@dataclass
class ProviderInfo:
    """Identifies which provider/model handled a request."""
    provider: str          # e.g. "argos", "faster_whisper", "kokoro"
    model: str             # e.g. "opus-mt-en-hi"
    version: str = ""
    device: str = "cpu"    # "cpu" | "cuda" | "mps"


@dataclass
class STTResult:
    """Output from a speech-to-text provider."""
    text: str
    language: str
    language_probability: float = 0.0
    confidence: float = 0.0
    duration_ms: float = 0.0
    provider: ProviderInfo | None = None
    segments: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TTSResult:
    """Output from a text-to-speech provider."""
    audio_bytes: bytes
    sample_rate: int = 22050
    format: str = "wav"
    duration_ms: float = 0.0
    provider: ProviderInfo | None = None


# ---------------------------------------------------------------------------
# Router & Inference Layer Types
# ---------------------------------------------------------------------------

class Task(str, Enum):
    STT = "stt"
    MT = "mt"
    TTS = "tts"
    LANG_DETECT = "lang_detect"
    SUMMARIZE = "summarize"
    EMBED = "embed"


@dataclass
class TranscriptChunk:
    text: str
    language: str | None
    is_final: bool
    start_ms: int = 0
    end_ms: int = 0
    confidence: float | None = None
    model: str = ""
    provider: str = ""


@dataclass
class AudioChunk:
    """PCM audio chunk. sample_rate/mono 16-bit signed LE unless stated."""
    data: bytes
    sample_rate: int = 24000
    encoding: str = "pcm_s16le"
    format: str = "wav"
    provider: str = ""
    model: str = ""
    duration_ms: float = 0.0
    is_dev: bool = False


@dataclass
class DetectionResult:
    language: str
    confidence: float
    provider: str
    alternatives: list[tuple[str, float]] = field(default_factory=list)


@dataclass
class RouteDecision:
    provider: str
    model: str
    task: Task
    reason: str
    latency_budget_ms: float | None = None
    started_at: float = field(default_factory=time.time)


@dataclass
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

