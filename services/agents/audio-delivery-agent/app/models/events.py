"""Structured events emitted by Agent 07 Audio Delivery Agent."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class BaseDeliveryEvent(BaseModel):
    version: int = 1
    type: str
    room_id: str
    session_id: str
    speaker_id: Optional[str] = None
    segment_id: Optional[str] = None
    utterance_id: Optional[str] = None
    target_lang: Optional[str] = None
    created_at: float = Field(default_factory=time.time)


class AudioQueuedEvent(BaseDeliveryEvent):
    """Emitted when an incoming audio chunk enters the jitter buffer."""
    type: str = "audio.queued"
    chunk_index: int
    is_final_chunk: bool = False
    buffer_depth: int = 0
    duration_ms: float = 0.0


class AudioSynchronizedEvent(BaseDeliveryEvent):
    """Emitted when a chunk has passed reordering and is scheduled on the timeline."""
    type: str = "audio.synchronized"
    chunk_index: int
    scheduled_wall_ms: float
    time_offset_ms: float = 0.0


class AudioPublishedEvent(BaseDeliveryEvent):
    """Emitted when audio has been successfully dispatched to transport (LiveKit/WS)."""
    type: str = "audio.published"
    track: str
    seq: int = 1
    chunk_index: int
    recipients_count: int
    recipient_ids: List[str]
    transport: str  # livekit | websocket_binary | websocket_json


class AudioPlaybackStartedEvent(BaseDeliveryEvent):
    """Emitted when playback begins for an utterance."""
    type: str = "audio.playback.started"
    estimated_duration_ms: float


class AudioPlaybackCompletedEvent(BaseDeliveryEvent):
    """Emitted when all chunks for an utterance have finished playing."""
    type: str = "audio.playback.completed"
    total_chunks: int
    total_duration_ms: float


class AudioDroppedEvent(BaseDeliveryEvent):
    """Emitted when a chunk or utterance is dropped due to staleness, duplicate, or queue limit."""
    type: str = "audio.dropped"
    chunk_index: Optional[int] = None
    reason: str  # stale_deadline_exceeded | duplicate_chunk | queue_overflow | room_closed


class AudioCancelledEvent(BaseDeliveryEvent):
    """Emitted when an utterance is aborted due to barge-in interruption."""
    type: str = "audio.cancelled"
    reason: str = "barge_in_interruption"
    flushed_chunks_count: int = 0


class AudioDeliveryFailedEvent(BaseDeliveryEvent):
    """Emitted when transport delivery encounters a network or framing failure."""
    type: str = "audio.delivery.failed"
    error_code: str
    error_message: str

