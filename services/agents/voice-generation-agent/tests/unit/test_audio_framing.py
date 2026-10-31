"""Unit tests for TalkFlow binary audio wire framing."""
import pytest
from app.audio.binary_framing import build_binary_tts_frame, decode_binary_tts_frame


def test_binary_framing_roundtrip():
    seg_id = "12345678-abcd-1234-cdef-123456789abc"
    target_lang = "hi"
    chunk_index = 3
    pcm_payload = b"\x01\x02\x03\x04\x05\x06"

    # Encode
    frame = build_binary_tts_frame(
        segment_id=seg_id,
        target_lang=target_lang,
        chunk_index=chunk_index,
        audio_pcm_bytes=pcm_payload,
        include_chunk_index=True,
    )

    # Magic byte assertion
    assert frame[0] == 0x54  # 'T'

    # Decode
    decoded = decode_binary_tts_frame(frame)
    assert decoded["kind"] == "tts"
    assert decoded["language"] == target_lang
    assert decoded["chunk_index"] == chunk_index
    assert decoded["pcm"] == pcm_payload
    assert decoded["short_id"] == "12345678abcd1234"


def test_binary_framing_invalid_magic_byte():
    bad_frame = b"\x00" + b" " * 30
    with pytest.raises(ValueError) as exc:
        decode_binary_tts_frame(bad_frame)
    assert "Invalid magic byte" in str(exc.value)

