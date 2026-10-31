"""TalkFlow event schemas for real-time translation pipelines."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class LanguageSpan(BaseModel):
    text: str
    language: str
    script: str = "Latn"
    start_char: Optional[int] = 0
    end_char: Optional[int] = 0
    text_start_offset: Optional[int] = None
    text_end_offset: Optional[int] = None
    confidence: float = 1.0

    @model_validator(mode="before")
    @classmethod
    def populate_offsets(cls, values: Any) -> Any:
        if isinstance(values, dict):
            if "start_char" not in values and "text_start_offset" in values:
                values["start_char"] = values["text_start_offset"]
            if "end_char" not in values and "text_end_offset" in values:
                values["end_char"] = values["text_end_offset"]
        return values


class Agent03TranscriptEvent(BaseModel):
    """Inbound event from Agent 03 (Language Intelligence Agent)."""
    version: int = 1
    type: str = "language.analysis.final"
    session_id: str
    conversation_id: str
    speaker_id: str = "user_001"
    utterance_id: str
    segment_id: str
    seq: int = 1
    original_text: str
    primary_language: str
    secondary_languages: List[str] = Field(default_factory=list)
    is_multilingual: bool = False
    confidence: float = 1.0
    detection_status: str = "success"
    language_spans: List[LanguageSpan] = Field(default_factory=list)
    routing_directive: Optional[str] = None
    target_languages: List[str] = Field(default_factory=lambda: ["en"])


class TranslationPartialEvent(BaseModel):
    """Provisional streaming translation event."""
    version: int = 1
    type: str = "translation.partial"
    session_id: str
    conversation_id: str
    speaker_id: str
    utterance_id: str
    segment_id: str
    source_lang: str
    target_lang: str
    revision: int = 1
    source_text_revision: int = 1
    text: str
    is_final: bool = False
    provider: str
    model: str
    quality_flags: List[str] = Field(default_factory=list)


class TranslationFinalEvent(BaseModel):
    """Final immutable translation event sent to Agent 05 and TalkFlow Hub."""
    version: int = 1
    type: str = "translation.final"
    session_id: str
    conversation_id: str
    speaker_id: str
    utterance_id: str
    segment_id: str
    seq: int = 1
    source_lang: str
    target_lang: str
    source_text: str
    text: str
    is_final: bool = True
    provider: str
    model: str
    latency_ms: float
    confidence: Optional[float] = None
    quality_flags: List[str] = Field(default_factory=list)
    tm_match: Optional[str] = None
    glossary_applied: bool = False
    pivoted: bool = False
    source_equals_target: bool = False


class TranslationFailedEvent(BaseModel):
    """Explicit failure event when translation cannot be produced."""
    version: int = 1
    type: str = "translation.failed"
    session_id: str
    conversation_id: str
    speaker_id: str
    utterance_id: str
    segment_id: str
    source_lang: str
    target_lang: str
    status: str = "failed"
    recoverable: bool = True
    reason_code: str
    user_message: str

