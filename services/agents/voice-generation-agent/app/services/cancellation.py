"""Utterance Cancellation Registry for Agent 06."""
from __future__ import annotations

import time
from typing import Dict, Set
from app.core.logging import get_logger

logger = get_logger(__name__)


class CancellationManager:
    """Tracks active cancellation tokens for interrupted or cancelled utterances."""

    def __init__(self) -> None:
        # segment_id -> cancel timestamp
        self._cancelled_segments: Dict[str, float] = {}
        # conversation_id -> cancel timestamp
        self._cancelled_conversations: Dict[str, float] = {}

    def cancel_segment(self, conversation_id: str, segment_id: str) -> None:
        """Mark a specific utterance segment as cancelled."""
        now = time.time()
        self._cancelled_segments[segment_id] = now
        logger.info(
            "Cancelled TTS segment",
            extra={"conversation_id": conversation_id, "segment_id": segment_id},
        )

    def cancel_conversation(self, conversation_id: str) -> None:
        """Mark an entire conversation as cancelled."""
        now = time.time()
        self._cancelled_conversations[conversation_id] = now
        logger.info("Cancelled all TTS in conversation", extra={"conversation_id": conversation_id})

    def is_cancelled(self, conversation_id: str, segment_id: str) -> bool:
        """Check if an utterance or conversation was cancelled."""
        if conversation_id in self._cancelled_conversations:
            return True
        return segment_id in self._cancelled_segments

    def prune_old(self, max_age_seconds: float = 3600.0) -> None:
        """Prune cancellation records older than max_age_seconds."""
        now = time.time()
        self._cancelled_segments = {
            k: v for k, v in self._cancelled_segments.items() if now - v < max_age_seconds
        }
        self._cancelled_conversations = {
            k: v for k, v in self._cancelled_conversations.items() if now - v < max_age_seconds
        }

