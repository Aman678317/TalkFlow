"""Event envelopes and schemas matching TalkFlow / GlobalTalk protocol."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


def current_iso_time() -> str:
    return datetime.now(timezone.utc).isoformat()


class BaseTalkFlowEvent(BaseModel):
    version: int = 1
    event: str
    session_id: str
    conversation_id: str
    speaker_id: str
    sequence: int
    timestamp: str = Field(default_factory=current_iso_time)


class AudioFrameInputEvent(BaseTalkFlowEvent):
    """Incoming audio frame metadata event (accompanies binary payload)."""
    event: str = "audio.frame"
    sample_rate: int = 16000
    channels: int = 1
    encoding: str = "pcm_s16le"
    frame_duration_ms: int = 50


class SpeechStartedEvent(BaseTalkFlowEvent):
    """Emitted when voice activity starts for a speaker."""
    event: str = "speech.started"
    mono_ms: int
    segment_id: str


class SpeechEndedEvent(BaseTalkFlowEvent):
    """Emitted when voice activity ends for a speaker."""
    event: str = "speech.ended"
    duration_ms: int
    segment_id: str


class AudioSegmentPartialEvent(BaseTalkFlowEvent):
    """Emitted incrementally during ongoing speech."""
    event: str = "audio.segment.partial"
    agent: str = "audio_intelligence"
    segment_id: str
    start_ms: int
    end_ms: int
    duration_ms: int
    sample_rate: int = 16000
    channels: int = 1
    encoding: str = "pcm_s16le"
    quality: Dict[str, Any]
    status: str = "partial"
    storage_ref: Optional[str] = None


class AudioSegmentFinalEvent(BaseTalkFlowEvent):
    """Emitted upon commitment of a finalized speech segment."""
    event: str = "audio.segment.final"
    agent: str = "audio_intelligence"
    segment_id: str
    start_ms: int
    end_ms: int
    duration_ms: int
    sample_rate: int = 16000
    channels: int = 1
    encoding: str = "pcm_s16le"
    quality: Dict[str, Any]
    status: str = "final"
    storage_ref: Optional[str] = None


class QualityDegradedEvent(BaseTalkFlowEvent):
    """Emitted when audio quality is compromised or degradation occurs."""
    event: str = "quality.degraded"
    agent: str = "audio_intelligence"
    reason: str
    user_message: str
    recoverable: bool = True

