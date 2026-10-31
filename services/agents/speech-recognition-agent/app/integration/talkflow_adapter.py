"""TalkFlow native protocol and wire format adapter."""
from __future__ import annotations

from typing import Any, Dict
from app.models.events import TranscriptFinalEvent, TranscriptPartialEvent


class TalkFlowAdapter:
    """Encodes and formats STT events for native TalkFlow event bus and WebSocket consumers."""

    @staticmethod
    def format_partial_event(event: TranscriptPartialEvent) -> Dict[str, Any]:
        """Formats transcript.partial event for TalkFlow."""
        return {
            "version": 1,
            "type": "transcript.partial",
            "session_id": event.session_id,
            "conversation_id": event.conversation_id,
            "speaker_id": event.speaker_id,
            "utterance_id": event.utterance_id,
            "segment_id": event.segment_id,
            "revision": event.revision,
            "text": event.text,
            "language": event.language_hint,
            "language_probability": event.language_probability,
            "is_final": False,
            "provider": event.provider,
            "model": event.model,
            "timestamp": event.timestamp,
        }

    @staticmethod
    def format_final_event(event: TranscriptFinalEvent) -> Dict[str, Any]:
        """Formats transcript.final event for TalkFlow and Agent 03."""
        return {
            "version": 1,
            "type": "transcript.final",
            "session_id": event.session_id,
            "conversation_id": event.conversation_id,
            "speaker_id": event.speaker_id,
            "utterance_id": event.utterance_id,
            "segment_id": event.segment_id,
            "sequence_hint": event.seq,
            "duration_ms": event.duration_ms,
            "text": event.text,
            "language": event.language_hint,
            "language_probability": event.language_probability,
            "confidence": event.confidence,
            "is_final": True,
            "provider": event.provider,
            "model": event.model,
            "recognition_latency_ms": event.recognition_latency_ms,
            "quality_flags": event.quality_flags,
            "segments": event.segments,
            "words": event.words,
            "timestamp": event.timestamp,
        }

