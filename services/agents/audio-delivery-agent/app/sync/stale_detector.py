"""Stale audio detection and conversation deadline enforcement."""
from __future__ import annotations

import time
from typing import Optional, Tuple
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import AudioChunkIngestRequest
from app.sync.timeline import TurnTimelineTracker

logger = get_logger("sync.stale_detector")


class StaleDetector:
    """Evaluates whether an audio chunk or utterance is too late to play safely."""

    def __init__(self, timeline: TurnTimelineTracker, max_stale_delay_ms: Optional[float] = None):
        settings = get_settings()
        self.timeline = timeline
        self.max_stale_delay_ms = (
            max_stale_delay_ms
            if max_stale_delay_ms is not None
            else float(settings.audio_sync.max_stale_delay_ms)
        )

    def is_chunk_stale(
        self, chunk: AudioChunkIngestRequest
    ) -> Tuple[bool, Optional[str]]:
        """Determine if chunk has expired past conversational deadlines.
        
        Returns:
            (is_stale, reason_string)
        """
        now_ms = time.time() * 1000.0

        # 1. Check if superseded by newer sequence turn from same speaker
        if self.timeline.is_superseded_by_newer_turn(chunk.session_id, chunk.speaker_id, chunk.seq):
            return True, f"superseded_by_newer_sequence_turn_seq_{chunk.seq}"

        # 2. Check if chunk start_wall_ms lags conversation horizon
        if chunk.start_wall_ms is not None and chunk.start_wall_ms > 0:
            age_ms = now_ms - chunk.start_wall_ms
            if age_ms > self.max_stale_delay_ms:
                return True, f"turn_start_wall_age_exceeded_{age_ms:.1f}ms_limit_{self.max_stale_delay_ms}ms"

        # 3. Check chunk generation created_at age
        if chunk.created_at > 0:
            gen_age_ms = (time.time() - chunk.created_at) * 1000.0
            # Allow reasonable leeway for multi-tier synthesis + network jitter
            if gen_age_ms > (self.max_stale_delay_ms * 2.5):
                return True, f"chunk_generation_age_exceeded_{gen_age_ms:.1f}ms"

        return False, None

