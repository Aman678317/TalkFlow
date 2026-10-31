"""TalkFlow wire protocol adapter for seamless integration with GlobalTalk."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
from app.models.events import AudioFrameInputEvent


class TalkFlowBinaryFrame:
    """TalkFlow dev WebSocket binary frame decoder/encoder.
    
    Format:
      byte 0:        'O' (0x4F, original mic) or 'T' (0x54, translated TTS)
      bytes 1..16:   16-character ASCII segment/utterance short ID
      byte 17:       language code length N (for 'T') or 0 (for 'O')
      bytes 18..:    language code ASCII (for 'T')
      rest:          PCM16 mono 16 kHz little-endian audio payload
    """
    ORIG = ord("O")
    TTS = ord("T")

    @classmethod
    def decode(cls, frame_bytes: bytes) -> Tuple[str, str, str, bytes]:
        """Decodes raw binary wire frame into (kind, short_id, language, pcm_bytes)."""
        if not frame_bytes or len(frame_bytes) < 17:
            return "original", "", "", frame_bytes

        kind = "original" if frame_bytes[0] == cls.ORIG else "tts"
        short_id = frame_bytes[1:17].decode("ascii", errors="replace").rstrip("\x00").rstrip("0")

        if kind == "tts" and len(frame_bytes) > 17:
            n = frame_bytes[17]
            lang = frame_bytes[18:18 + n].decode("ascii", errors="replace")
            pcm = frame_bytes[18 + n:]
        else:
            lang = ""
            pcm = frame_bytes[17:]

        return kind, short_id, lang, pcm

    @classmethod
    def encode_segment(cls, short_id: str, pcm_bytes: bytes) -> bytes:
        """Encodes an outgoing processed segment frame into TalkFlow's original binary format."""
        id_bytes = short_id.encode("ascii", errors="replace")[:16].ljust(16, b"0")
        return bytes([cls.ORIG]) + id_bytes + pcm_bytes


class TalkFlowAdapter:
    """Provides protocol translation between TalkFlow event contracts and Audio Intelligence Agent."""

    @staticmethod
    def parse_input_event(event_dict: Dict[str, Any]) -> AudioFrameInputEvent:
        """Parses incoming 'audio.frame' TalkFlow event."""
        return AudioFrameInputEvent(**event_dict)

    @staticmethod
    def format_output_event(
        event_type: str,
        session_id: str,
        conversation_id: str,
        speaker_id: str,
        segment_id: str,
        sequence: int,
        start_ms: int,
        end_ms: int,
        duration_ms: int,
        quality_dict: Dict[str, Any],
        status: str,
        storage_ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Formats TalkFlow contracted 'audio.segment.final' or 'audio.segment.partial' event."""
        return {
            "version": 1,
            "event": event_type,
            "agent": "audio_intelligence",
            "session_id": session_id,
            "conversation_id": conversation_id,
            "speaker_id": speaker_id,
            "segment_id": segment_id,
            "sequence": sequence,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "duration_ms": duration_ms,
            "sample_rate": 16000,
            "channels": 1,
            "encoding": "pcm_s16le",
            "quality": quality_dict,
            "status": status,
            "storage_ref": storage_ref,
        }

