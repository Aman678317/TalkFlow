"""Event schemas and envelopes matching TalkFlow multi-agent specifications."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.models.schemas import CandidateLanguage, LanguageSpan


class WordTiming(BaseModel):
    word: str
    start: float
    end: float
    confidence: float = 1.0

    @property
    def start_ms(self) -> int:
        return int(round(self.start * 1000))

    @property
    def end_ms(self) -> int:
        return int(round(self.end * 1000))


class InboundTranscriptEvent(BaseModel):
    """Inbound transcript event emitted by Agent 02 (Speech Recognition Agent)."""
    version: int = 1
    type: str  # "transcript.final" or "transcript.partial"
    session_id: str
    conversation_id: str
    speaker_id: str = "user_001"
    utterance_id: Optional[str] = None
    segment_id: Optional[str] = None
    seq: int = 1
    text: str
    language_hint: Optional[str] = None
    language_probability: Optional[float] = None
    confidence: Optional[float] = None
    is_final: bool = True
    provider: Optional[str] = None
    model: Optional[str] = None
    words: Optional[List[WordTiming]] = None
    speaker_preference: Optional[str] = None
    target_languages: Optional[List[str]] = None
    timestamp: float = Field(default_factory=time.time)


class LanguageAnalysisFinalEvent(BaseModel):
    """Outbound final language intelligence event forwarded to Agent 04 (Translation)."""
    version: int = 1
    type: str = "language.analysis.final"
    session_id: str
    conversation_id: str
    speaker_id: str
    utterance_id: str
    segment_id: str
    seq: int = 1
    original_text: str
    primary_language: str
    primary_language_script: str
    secondary_languages: List[str] = Field(default_factory=list)
    is_multilingual: bool = False
    detection_status: str = "success"
    confidence: float
    target_languages: List[str] = Field(default_factory=lambda: ["en", "hi", "mr"])
    language_spans: List[LanguageSpan] = Field(default_factory=list)
    uncertain_spans: List[LanguageSpan] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    capability_status: Dict[str, Any] = Field(default_factory=dict)
    provider: str = "language_intelligence"
    model_version: str = "1.0.0"
    timestamp: float = Field(default_factory=time.time)


class LanguageAnalysisUncertainEvent(BaseModel):
    """Outbound event when language evidence is insufficient or ambiguous."""
    version: int = 1
    type: str = "language.analysis.uncertain"
    session_id: str
    speaker_id: str
    utterance_id: str
    original_text: str
    primary_language: str = "und"
    detection_status: str = "insufficient_confidence"
    confidence: float = 0.0
    candidates: List[CandidateLanguage] = Field(default_factory=list)
    reason: str = "insufficient_text_evidence"
    timestamp: float = Field(default_factory=time.time)
