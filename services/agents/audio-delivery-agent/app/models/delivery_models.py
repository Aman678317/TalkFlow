"""Domain models for rooms, participant routing, and audio tracks."""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Set
from pydantic import BaseModel, Field


class ParticipantRoute(BaseModel):
    """Routing and playback preference profile for a single meeting participant."""
    participant_id: str
    room_id: str
    tenant_id: str = "org_default"
    display_name: str = "Participant"
    hear_lang: str = "en"
    speaking_lang: str = "en"
    playback_mode: str = "translated"  # original | translated | both | muted
    translation_audio_enabled: bool = True
    original_audio_enabled: bool = False
    captions_enabled: bool = True
    is_connected: bool = True
    supports_tts_chunk_index: bool = True
    connected_at: float = Field(default_factory=time.time)
    last_seen_at: float = Field(default_factory=time.time)


class AudioTrackInfo(BaseModel):
    """Metadata identifying an audio delivery stream track in a room."""
    track_id: str
    room_id: str
    target_lang: str
    track_name: str  # e.g., 'gt-translated-hi'
    sample_rate: int = 24000
    channels: int = 1
    encoding: str = "pcm_s16le"
    format: str = "wav"
    synthetic: bool = True
    audio_origin: str = "synthetic_tts"
    active_listeners_count: int = 0
    created_at: float = Field(default_factory=time.time)


class RoomSession(BaseModel):
    """In-memory state of an active meeting room."""
    room_id: str
    tenant_id: str = "org_default"
    created_at: float = Field(default_factory=time.time)
    participants: Dict[str, ParticipantRoute] = Field(default_factory=dict)
    active_tracks: Dict[str, AudioTrackInfo] = Field(default_factory=dict)
    active_utterance_ids: Set[str] = Field(default_factory=set)
    is_active: bool = True

