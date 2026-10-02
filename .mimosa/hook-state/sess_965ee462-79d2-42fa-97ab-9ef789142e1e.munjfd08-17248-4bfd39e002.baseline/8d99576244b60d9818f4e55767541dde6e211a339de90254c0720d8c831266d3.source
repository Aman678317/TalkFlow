"""Versioned realtime WebSocket protocol (section 11).

Every server event: {version, type, session_id, conversation_id, speaker_id?, sequence,
timestamp, ...payload}. Sequence numbers are per-conversation, monotonic, assigned by the
hub (deterministic infrastructure — never by AI agents). Clients resume with last_sequence.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

PROTOCOL_VERSION = 1


class EventType:
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
    TTS_COMPLETED = "tts.completed"
    AUDIO_PUBLISHED = "audio.published"
    CAPTION_UPDATED = "caption.updated"
    LANGUAGE_CHANGED = "language.changed"
    CHAT_MESSAGE = "chat.message"
    CHAT_TRANSLATION = "chat.translation"
    QUALITY_DEGRADED = "quality.degraded"
    QUALITY_LATENCY = "quality.latency"
    TRANSLATION_FAILED = "translation.failed"
    RECONNECT_REQUIRED = "reconnect.required"
    ERROR = "error"
    PONG = "pong"


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_event(event_type: str, *, session_id: str, conversation_id: str,
               sequence: int | None = None, **payload: Any) -> dict[str, Any]:
    return {
        "version": PROTOCOL_VERSION,
        "type": event_type,
        "session_id": session_id,
        "conversation_id": conversation_id,
        "sequence": sequence,
        "timestamp": iso_now(),
        **payload,
    }


def client_event_type(data: dict[str, Any]) -> str:
    return str(data.get("type", ""))


class BinaryFrame:
    """Binary audio frame layout (dev WebSocket transport; LiveKit replaces this in prod):

    byte 0     : 'O' (0x4F) original-audio relay | 'T' (0x54) translated TTS PCM
    bytes 1-16 : 16-char ASCII utterance/segment short-id
    byte 17    : language code length N (for 'T' only; 0 for 'O')
    bytes 18.. : N-char ASCII language code (for 'T')
    rest       : PCM16 mono @16kHz little-endian
    """

    ORIG = ord("O")
    TTS = ord("T")

    @staticmethod
    def encode_original(short_id: str, pcm: bytes) -> bytes:
        return bytes([BinaryFrame.ORIG]) + short_id.encode()[:16].ljust(16, b"0") + pcm

    @staticmethod
    def encode_tts(short_id: str, language: str, pcm: bytes) -> bytes:
        lang = language.encode()[:8]
        return (bytes([BinaryFrame.TTS]) + short_id.encode()[:16].ljust(16, b"0")
                + bytes([len(lang)]) + lang + pcm)

    @staticmethod
    def decode(frame: bytes) -> tuple[str, str, str, bytes]:
        kind = "original" if frame[0] == BinaryFrame.ORIG else "tts"
        short_id = frame[1:17].decode(errors="replace").rstrip("0")
        if kind == "tts":
            n = frame[17]
            lang = frame[18:18 + n].decode()
            pcm = frame[18 + n:]
        else:
            lang, pcm = "", frame[17:]
        return kind, short_id, lang, pcm
