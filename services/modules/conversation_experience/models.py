"""Data models for Natural Conversation Experience (Module H)."""
from __future__ import annotations

import time
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class TurnEvent(BaseModel):
    """Real-time speaker turn boundary event."""
    speaker_id: str
    event_type: str  # 'turn_start', 'turn_end', 'backchannel', 'interruption'
    timestamp_ms: int
    duration_ms: int = 0
    text: str = ""
    is_backchannel: bool = False
    interrupted_speaker_id: Optional[str] = None


class AcousticState(BaseModel):
    """Room acoustic and playback control state."""
    room_id: str
    active_speaker_id: Optional[str] = None
    is_speaking: bool = False
    is_interrupted: bool = False
    current_playback_ducking_db: float = 0.0  # 0dB = normal, -18dB = ducked, -90dB = muted
    noise_floor_db: float = -45.0
    jitter_buffer_depth_ms: int = 60

