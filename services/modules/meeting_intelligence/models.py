"""Data models for AI Meeting Intelligence & Ask Meeting AI (Module C)."""
from __future__ import annotations

import time
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class TranscriptTurn(BaseModel):
    """A single speaker turn with timestamps and language metadata."""
    turn_id: str
    speaker_id: str
    speaker_name: str
    start_ms: int
    end_ms: int
    language: str
    text: str
    confidence: float = 0.95


class ActionItem(BaseModel):
    """An identified action item from the meeting."""
    item_id: str
    task: str
    assignee: str = "Unassigned"
    deadline: Optional[str] = None
    priority: str = "medium"  # 'high', 'medium', 'low'
    source_turn_id: Optional[str] = None
    source_timestamp: str = ""


class MeetingIntelligenceReport(BaseModel):
    """Comprehensive AI Meeting Intelligence Dossier."""
    meeting_id: str
    tenant_id: str = "org_default"
    title: str = "Multilingual Project Meeting"
    created_at: float = Field(default_factory=time.time)
    duration_sec: float = 0.0
    participant_names: List[str] = Field(default_factory=list)
    languages_spoken: List[str] = Field(default_factory=list)
    
    # Transcripts
    full_transcript_chronological: str = ""
    speaker_turns: List[TranscriptTurn] = Field(default_factory=list)
    
    # Intelligence Synthesis
    executive_summary: str = ""
    key_discussions: List[str] = Field(default_factory=list)
    decisions_made: List[str] = Field(default_factory=list)
    action_items: List[ActionItem] = Field(default_factory=list)
    important_timestamps: List[Dict[str, str]] = Field(default_factory=list)
    
    # Multilingual Notes
    notes_language: str = "en"
    translated_summary: Optional[str] = None
    translated_action_items: Optional[List[Dict[str, str]]] = None


class AskMeetingAIQuery(BaseModel):
    """Query payload for asking questions about meeting content."""
    meeting_id: str
    tenant_id: str = "org_default"
    question: str
    preferred_language: str = "en"


class AskMeetingAIResponse(BaseModel):
    """Grounded answer from Ask Meeting AI with citations and timestamps."""
    meeting_id: str
    question: str
    answer: str
    cited_turns: List[TranscriptTurn] = Field(default_factory=list)
    source_timestamps: List[str] = Field(default_factory=list)
    confidence: float = 0.95
    latency_ms: float = 0.0

