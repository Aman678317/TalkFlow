"""Unit tests for TalkFlow 0x54 binary audio wire protocol."""
from __future__ import annotations

import pytest
from app.core.exceptions import AudioFramingError
from app.transport.binary_wire import (
    TAG_TTS_BYTE,
    decode_talkflow_binary_frame,
    encode_talkflow_binary_frame,
)


def test_binary_wire_encode_decode():
    """Verify that binary wire frame conforms to TalkFlow layout and decodes accurately."""
    seg_id = "123e4567-e89b-12d3-a456-426614174000"
    target_lang = "mr"
    chunk_index = 42
    pcm_payload = b"\x00\x01\x02\x03" * 100

    frame = encode_talkflow_binary_frame(
        segment_id=seg_id,
        target_lang=target_lang,
        chunk_index=chunk_index,
        audio_bytes=pcm_payload,
        supports_tts_chunk_index=True,
    )

    # Validate header magic byte
    assert frame[0:1] == TAG_TTS_BYTE  # 0x54

    # Decode and assert roundtrip integrity
    decoded = decode_talkflow_binary_frame(frame)
    assert decoded["target_lang"] == "mr"
    assert decoded["chunk_index"] == 42
    assert decoded["has_extension"] is True
    assert decoded["audio_bytes"] == pcm_payload
    assert decoded["audio_len"] == len(pcm_payload)


def test_binary_wire_legacy_without_extension():
    """Verify framing without extension chunk index."""
    seg_id = "test_seg_legacy"
    target_lang = "hi"
    pcm_payload = b"\x10\x20\x30\x40"

    frame = encode_talkflow_binary_frame(
        segment_id=seg_id,
        target_lang=target_lang,
        chunk_index=0,
        audio_bytes=pcm_payload,
        supports_tts_chunk_index=False,
    )

    decoded = decode_talkflow_binary_frame(frame)
    assert decoded["target_lang"] == "hi"
    assert decoded["audio_bytes"] == pcm_payload


def test_binary_wire_invalid_tag():
    """Verify that frame with invalid tag is rejected."""
    bad_frame = b"\x41" + b"\x00" * 30
    with pytest.raises(AudioFramingError):
        decode_talkflow_binary_frame(bad_frame)

