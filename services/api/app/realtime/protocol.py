"""Versioned realtime WebSocket protocol (PDD §11, §14).

Every server event carries: version, type, session_id, conversation_id,
sequence (monotonic per session), timestamp. Clients dedupe by sequence and
resume after reconnect by sending the last seen sequence.

Event envelope is a Pydantic model — NO untyped realtime events (PDD §72).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ServerEventType(StrEnum):
    SESSION_CREATED = "session.created"
    SESSION_UPDATED = "session.updated"
    SESSION_RESUMED = "session.resumed"
    PARTICIPANT_JOINED = "participant.joined"
    PARTICIPANT_LEFT = "participant.left"
    AUDIO_STARTED = "audio.started"
    AUDIO_STOPPED = "audio.stopped"
    SPEECH_STARTED = "speech.started"
    SPEECH_ENDED = "speech.ended"
    TRANSCRIPT_PARTIAL = "transcript.partial"
    TRANSCRIPT_FINAL = "transcript.final"
    TRANSLATION_STARTED = "translation.started"
    TRANSLATION_PARTIAL = "translation.partial"
    TRANSLATION_FINAL = "translation.final"
    TTS_STARTED = "tts.started"
    TTS_CHUNK = "tts.chunk"
    TTS_COMPLETED = "tts.completed"
    AUDIO_PUBLISHED = "audio.published"
    CAPTION_UPDATED = "caption.updated"
    LANGUAGE_CHANGED = "language.changed"
    QUALITY_DEGRADED = "quality.degraded"
    TRANSLATION_FAILED = "translation.failed"
    RECONNECT_REQUIRED = "reconnect.required"
    CHAT_MESSAGE = "chat.message"
    LATENCY_REPORT = "latency.report"
    MEDIA_STATE = "media.state"
    SIGNAL = "signal"
    PONG = "pong"
    ERROR = "error"
    # Prompt event contract aliases
    TRANSLATION_TRANSCRIPT_PARTIAL = "translation.transcript.partial"
    TRANSLATION_TRANSCRIPT_FINAL = "translation.transcript.final"
    TRANSLATION_SEGMENT_TRANSLATED = "translation.segment.translated"
    TRANSLATION_SEGMENT_FINAL = "translation.segment.final"
    TRANSLATION_TTS_READY = "translation.tts.ready"
    TRANSLATION_STATUS = "translation.status"
    TRANSLATION_ERROR = "translation.error"


class ClientEventType(StrEnum):
    SESSION_JOIN = "session.join"
    SESSION_RESUME = "session.resume"
    AUDIO_START = "audio.start"
    AUDIO_CHUNK = "audio.chunk"        # base64 in JSON; binary frames preferred
    AUDIO_STOP = "audio.stop"
    TRANSCRIPT_INJECT = "transcript.inject"  # dev/test only (guarded server-side)
    PREFERENCES_UPDATE = "preferences.update"
    CHAT_SEND = "chat.send"
    MEDIA_STATE = "media.state"
    SIGNAL = "signal"
    PING = "ping"


PROTOCOL_VERSION = 1


class ServerEvent(BaseModel):
    version: int = PROTOCOL_VERSION
    type: str
    session_id: str = ""
    conversation_id: str = ""          # meeting id
    speaker_id: str | None = None
    sequence: int = 0                  # per-session monotonic; 0 = non-sequenced
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    data: dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        payload = self.model_dump(exclude_none=False)
        data = payload.get("data") or {}
        merged = {**data, **payload, "data": data}
        if "segment_id" in merged and "utterance_id" not in merged:
            merged["utterance_id"] = merged["segment_id"]
        if "speaker_name" in merged and "display_name" not in merged:
            merged["display_name"] = merged["speaker_name"]
        if "source_lang" in merged and "source_language" not in merged:
            merged["source_language"] = merged["source_lang"]
        if "target_lang" in merged and "target_language" not in merged:
            merged["target_language"] = merged["target_lang"]
        return json.dumps(merged)


class ClientEvent(BaseModel):
    version: int = PROTOCOL_VERSION
    type: str
    session_id: str = ""
    sequence: int | None = None        # client-side idempotency key
    timestamp: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


def parse_client_event(raw: str | bytes) -> ClientEvent:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Invalid client event: must be JSON object.")
    if "data" not in payload or not isinstance(payload["data"], dict):
        payload["data"] = {
            k: v for k, v in payload.items()
            if k not in ("version", "type", "session_id", "sequence", "timestamp")
        }
    else:
        for k, v in payload.items():
            if k not in ("version", "type", "session_id", "sequence", "timestamp", "data") and k not in payload["data"]:
                payload["data"][k] = v
    return ClientEvent.model_validate(payload)


# --------------------------------------------------------------------------- #
# Convenience constructors (keep event shapes consistent everywhere)
# --------------------------------------------------------------------------- #

def transcript_partial(session_id: str, conversation_id: str, speaker_id: str,
                       seq: int, language: str, text: str,
                       is_final: bool = False, **extra) -> dict:
    return {
        "version": PROTOCOL_VERSION,
        "type": ServerEventType.TRANSCRIPT_PARTIAL if not is_final
                else ServerEventType.TRANSCRIPT_FINAL,
        "session_id": session_id,
        "conversation_id": conversation_id,
        "speaker_id": speaker_id,
        "sequence": seq,
        "language": language,
        "text": text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "is_final": is_final,
        **extra,
    }


class LatencyTrace(BaseModel):
    """PDD §10 — every stage measured, reported via latency.report."""
    segment_id: str = ""
    seq: int = 0
    source_lang: str = ""
    target_lang: str = ""
    audio_capture_ms: float = 0
    stt_first_partial_ms: float = 0
    stt_final_ms: float = 0
    translation_ms: float = 0
    tts_first_audio_ms: float = 0
    delivery_ms: float = 0
    total_e2e_latency_ms: float = 0
    stale_dropped: bool = False
