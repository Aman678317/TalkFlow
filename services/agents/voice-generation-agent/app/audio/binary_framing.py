"""TalkFlow Binary Audio Framing Implementation.

Implements the exact wire contract between TalkFlow TTS pipeline and delivery clients:
- Prefix byte 0x54 ('T')
- 16-byte short ID (derived from segment_id UUID)
- 1-byte language length + UTF-8 language bytes
- Extension byte 0x01 + 4-byte big-endian uint32 chunk sequence index
- Raw audio PCM bytes
"""
from __future__ import annotations

import struct
from typing import Any, Dict, Optional, Union
import uuid


def build_binary_tts_frame(
    segment_id: Union[uuid.UUID, str],
    target_lang: str,
    chunk_index: int,
    audio_pcm_bytes: bytes,
    include_chunk_index: bool = True,
) -> bytes:
    """Encode an audio chunk into TalkFlow binary wire frame."""
    clean_id = str(segment_id).replace("-", "")[:16]
    short_id_bytes = clean_id.ljust(16, "\x00").encode("utf-8")
    lang_bytes = target_lang.encode("utf-8")

    prefix = b"\x54" + short_id_bytes + bytes([len(lang_bytes)]) + lang_bytes

    extension = (
        b"\x01" + int(chunk_index).to_bytes(4, "big", signed=False)
        if include_chunk_index
        else b""
    )
    return prefix + extension + audio_pcm_bytes


def decode_binary_tts_frame(buf: bytes) -> Dict[str, Any]:
    """Decode a TalkFlow binary frame for verification and test assertions."""
    if not buf or len(buf) < 18:
        raise ValueError(f"Buffer too short for TalkFlow binary frame: {len(buf)} bytes")

    if buf[0] != 0x54:  # ord('T') == 84 == 0x54
        raise ValueError(f"Invalid magic byte 0x{buf[0]:02x}, expected 0x54 ('T')")

    short_id = buf[1:17].decode("utf-8", errors="replace").replace("\x00", "")
    lang_len = buf[17]
    payload_start = 18 + lang_len

    if len(buf) < payload_start:
        raise ValueError("Buffer truncated before language tag payload")

    lang = buf[18:payload_start].decode("utf-8", errors="replace")

    chunk_index: Optional[int] = None
    if len(buf) >= payload_start + 5 and buf[payload_start] == 0x01:
        chunk_index = struct.unpack(">I", buf[payload_start + 1 : payload_start + 5])[0]
        pcm = buf[payload_start + 5 :]
    else:
        pcm = buf[payload_start:]

    return {
        "kind": "tts",
        "short_id": short_id,
        "language": lang,
        "chunk_index": chunk_index,
        "pcm": pcm,
        "pcm_bytes_count": len(pcm),
    }

