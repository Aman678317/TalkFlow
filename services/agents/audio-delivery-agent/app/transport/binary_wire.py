"""TalkFlow 0x54 ('T') binary audio wire framing and decoder."""
from __future__ import annotations

import struct
from typing import Any, Dict, Optional, Tuple
from app.core.exceptions import AudioFramingError
from app.core.logging import get_logger

logger = get_logger("transport.binary_wire")

TAG_TTS_BYTE = b"\x54"  # ASCII 'T'
EXTENSION_CHUNK_INDEX_MARKER = b"\x01"


def encode_talkflow_binary_frame(
    segment_id: str,
    target_lang: str,
    chunk_index: int,
    audio_bytes: bytes,
    supports_tts_chunk_index: bool = True,
) -> bytes:
    """Encode an audio chunk into TalkFlow's low-latency binary wire format.
    
    Wire layout:
    - Byte 0: 0x54 ('T')
    - Bytes 1..16: 16-byte fixed-width short ID (segment UUID hex without dashes, padded with \x00)
    - Byte 17: uint8 length of target_lang string (L)
    - Bytes 18..(18+L-1): target_lang UTF-8 bytes
    - Optional extension (if supports_tts_chunk_index):
        - Byte (18+L): 0x01 marker
        - Bytes (19+L)..(22+L): uint32 chunk_index in big-endian
    - Remaining bytes: raw audio payload (PCM16 / WAV bytes)
    """
    try:
        short_id_bytes = str(segment_id).replace("-", "")[:16].ljust(16, "\x00").encode("utf-8")
        lang_bytes = target_lang.encode("utf-8")
        lang_len = len(lang_bytes)

        if lang_len > 255:
            raise AudioFramingError(f"Target language tag length exceeds 255 bytes: {target_lang}")

        header = TAG_TTS_BYTE + short_id_bytes + bytes([lang_len]) + lang_bytes

        if supports_tts_chunk_index:
            extension = EXTENSION_CHUNK_INDEX_MARKER + struct.pack(">I", int(chunk_index))
            frame = header + extension + audio_bytes
        else:
            frame = header + audio_bytes

        return frame
    except Exception as exc:
        logger.error(
            "Failed to encode TalkFlow binary frame",
            extra={"segment_id": segment_id, "target_lang": target_lang, "error": str(exc)}
        )
        raise AudioFramingError(f"Binary wire encoding failed: {exc}") from exc


def decode_talkflow_binary_frame(frame: bytes) -> Dict[str, Any]:
    """Decode a TalkFlow binary frame into its header components and audio payload."""
    if len(frame) < 18:
        raise AudioFramingError(f"Binary frame too short: {len(frame)} bytes")

    if frame[0:1] != TAG_TTS_BYTE:
        raise AudioFramingError(f"Invalid frame tag: expected 0x54 ('T'), got {frame[0:1]!r}")

    short_id_raw = frame[1:17].decode("utf-8", errors="replace").rstrip("\x00")
    lang_len = frame[17]

    offset = 18
    if len(frame) < offset + lang_len:
        raise AudioFramingError("Binary frame truncated before language string")

    target_lang = frame[offset : offset + lang_len].decode("utf-8", errors="replace")
    offset += lang_len

    chunk_index = 0
    has_chunk_index_ext = False

    # Check for extension marker 0x01
    if len(frame) >= offset + 5 and frame[offset : offset + 1] == EXTENSION_CHUNK_INDEX_MARKER:
        has_chunk_index_ext = True
        offset += 1
        chunk_index = struct.unpack(">I", frame[offset : offset + 4])[0]
        offset += 4

    audio_bytes = frame[offset:]

    return {
        "short_id": short_id_raw,
        "target_lang": target_lang,
        "chunk_index": chunk_index,
        "has_extension": has_chunk_index_ext,
        "audio_bytes": audio_bytes,
        "audio_len": len(audio_bytes),
    }

