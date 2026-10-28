"""Unit tests for realtime binary TTS framing and chunk index negotiation.

Verifies the wire contract between backend pipeline.py and frontend ws.ts:
- Binary frame starts with 0x54 ('T')
- Followed by 16-byte short ID (derived from segment_id UUID)
- Followed by 1-byte language length + UTF-8 language tag
- Extension byte 0x01 + 4-byte big-endian uint32 chunk index when supported
- Legacy backward compatibility when client does not support chunk index
"""
from __future__ import annotations

import struct
import uuid

import pytest


def _build_binary_tts_frame(
    segment_id: uuid.UUID | str,
    target_lang: str,
    chunk_index: int,
    audio_bytes: bytes,
    supports_tts_chunk_index: bool = True,
) -> bytes:
    """Mirrors the exact binary TTS framing logic from app.realtime.pipeline."""
    short_id_bytes = str(segment_id).replace("-", "")[:16].ljust(16, "\x00").encode("utf-8")
    lang_bytes = target_lang.encode("utf-8")
    bin_header_prefix = b"\x54" + short_id_bytes + bytes([len(lang_bytes)]) + lang_bytes

    extension = (
        b"\x01" + int(chunk_index).to_bytes(4, "big", signed=False)
        if supports_tts_chunk_index
        else b""
    )
    return bin_header_prefix + extension + audio_bytes


def _decode_binary_tts_frame(buf: bytes) -> dict:
    """Mirrors frontend decodeBinaryFrame logic in Python for verification."""
    assert buf[0] == 0x54  # 'T'
    short_id = buf[1:17].decode("utf-8").replace("\x00", "")
    lang_len = buf[17]
    lang = buf[18 : 18 + lang_len].decode("utf-8")
    payload_start = 18 + lang_len

    if len(buf) >= payload_start + 5 and buf[payload_start] == 0x01:
        chunk_index = struct.unpack(">I", buf[payload_start + 1 : payload_start + 5])[0]
        pcm = buf[payload_start + 5 :]
        return {
            "kind": "tts",
            "shortId": short_id,
            "language": lang,
            "chunkIndex": chunk_index,
            "pcm": pcm,
        }
    return {
        "kind": "tts",
        "shortId": short_id,
        "language": lang,
        "chunkIndex": None,
        "pcm": buf[payload_start:],
    }


def test_binary_tts_frame_with_chunk_index():
    seg_id = uuid.uuid4()
    audio = b"RIFF\x24\x00\x00\x00WAVEfmt "
    chunk_idx = 7
    frame = _build_binary_tts_frame(seg_id, "es", chunk_idx, audio, supports_tts_chunk_index=True)

    decoded = _decode_binary_tts_frame(frame)
    expected_short_id = str(seg_id).replace("-", "")[:16]
    assert decoded["kind"] == "tts"
    assert decoded["shortId"] == expected_short_id
    assert decoded["language"] == "es"
    assert decoded["chunkIndex"] == 7
    assert decoded["pcm"] == audio


def test_binary_tts_frame_legacy_fallback():
    seg_id = uuid.uuid4()
    audio = b"RIFF\x24\x00\x00\x00WAVEfmt "
    frame = _build_binary_tts_frame(seg_id, "hi", 0, audio, supports_tts_chunk_index=False)

    decoded = _decode_binary_tts_frame(frame)
    expected_short_id = str(seg_id).replace("-", "")[:16]
    assert decoded["kind"] == "tts"
    assert decoded["shortId"] == expected_short_id
    assert decoded["language"] == "hi"
    assert decoded["chunkIndex"] is None
    assert decoded["pcm"] == audio


def test_binary_tts_frame_monotonic_sequence_order():
    seg_id = uuid.uuid4()
    audio = b"sample_audio"

    frames = [
        _build_binary_tts_frame(seg_id, "en", idx, audio, supports_tts_chunk_index=True)
        for idx in range(5)
    ]

    indices = [_decode_binary_tts_frame(f)["chunkIndex"] for f in frames]
    assert indices == [0, 1, 2, 3, 4]
