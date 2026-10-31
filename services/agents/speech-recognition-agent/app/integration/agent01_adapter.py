"""Adapter for ingesting structured audio events from Agent 01 (Audio Intelligence Agent)."""
from __future__ import annotations

import base64
from typing import Any, Dict, Optional, Tuple
from app.core.exceptions import AudioValidationError
from app.models.events import InboundAudioSegmentEvent


class Agent01Adapter:
    """Adapter for receiving clean audio chunks and events from Agent 01."""

    @staticmethod
    def parse_event(event_dict: Dict[str, Any]) -> InboundAudioSegmentEvent:
        """Parses and validates an inbound JSON event from Agent 01."""
        try:
            return InboundAudioSegmentEvent(**event_dict)
        except Exception as exc:
            raise AudioValidationError(f"Invalid Agent 01 event format: {exc}")

    @staticmethod
    def extract_pcm16_and_meta(
        event: InboundAudioSegmentEvent,
        raw_binary: Optional[bytes] = None,
    ) -> Tuple[bytes, Dict[str, Any]]:
        """Extracts PCM16 audio bytes and segment metadata from event or accompanying binary."""
        meta = {
            "session_id": event.session_id,
            "conversation_id": event.conversation_id,
            "speaker_id": event.speaker_id,
            "utterance_id": event.utterance_id or f"utt_{event.segment_id or 'unknown'}",
            "segment_id": event.segment_id or "seg_unknown",
            "seq": event.seq or 1,
            "start_ms": 0,
            "sample_rate": 16000,
            "is_final": event.type == "audio.segment.final",
        }

        if event.payload:
            meta["segment_id"] = event.payload.segment_id or meta["segment_id"]
            meta["seq"] = event.payload.sequence_number or meta["seq"]
            meta["start_ms"] = int(round(event.payload.start_timestamp * 1000))
            meta["sample_rate"] = event.payload.sample_rate
            meta["is_final"] = event.payload.is_final

            if event.payload.audio_data_base64:
                pcm16 = base64.b64decode(event.payload.audio_data_base64)
                return pcm16, meta

        if raw_binary:
            return raw_binary, meta

        raise AudioValidationError("No audio payload found in Agent 01 event")

