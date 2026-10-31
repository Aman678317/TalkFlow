"""Adapter for consuming and parsing inbound transcript events from Agent 02."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from app.models.events import InboundTranscriptEvent, WordTiming


class Agent02Adapter:
    """Parses Agent 02 transcript envelopes and word timings."""

    @staticmethod
    def parse_event(payload: Dict[str, Any]) -> InboundTranscriptEvent:
        """Parses a dictionary or JSON payload into an InboundTranscriptEvent."""
        words: List[WordTiming] = []
        raw_words = payload.get("words", [])
        for w in raw_words:
            if isinstance(w, dict):
                words.append(
                    WordTiming(
                        word=str(w.get("word", "")),
                        start_ms=int(round(float(w.get("start", 0.0)) * 1000)),
                        end_ms=int(round(float(w.get("end", 0.0)) * 1000)),
                        confidence=float(w.get("confidence", 1.0)),
                    )
                )

        return InboundTranscriptEvent(
            type=payload.get("type", "transcript.final"),
            session_id=str(payload.get("session_id", "sess_default")),
            conversation_id=str(payload.get("conversation_id", payload.get("session_id", "sess_default"))),
            speaker_id=str(payload.get("speaker_id", "user_001")),
            utterance_id=str(payload.get("utterance_id", "utt_default")),
            segment_id=str(payload.get("segment_id", "seg_default")),
            seq=int(payload.get("seq", 1)),
            text=str(payload.get("text", "")),
            language_hint=payload.get("language_hint") or payload.get("language"),
            language_probability=float(payload.get("language_probability", payload.get("confidence", 0.85))),
            is_final=bool(payload.get("is_final", True)),
            words=words,
        )

