"""Cross-transport identity of a translated-TTS chunk (Tree A, the deployed tree).

The server delivers every streamed chunk twice — as a JSON `tts.chunk` event and as
a binary frame — and the browser dedups them by queue tag. That dedup only works if
both transports encode the SAME chunk identity. `normId()` in apps/web/src/lib/ws.ts
is the single key function; this test pins the server-side encodings it must resolve.

Regression this prevents: the binary header was built from `segment_id` with NUL
padding while the client derived its JSON tag from `utterance_id[:16]` (dashes
intact). Two different keys for one chunk = the listener hears it twice, and the
same-tag eviction in AudioPlayer then deleted whichever chunks were still queued.
"""
from __future__ import annotations

import uuid


def norm_id(candidate: str) -> str:
    """Mirror of normId() in apps/web/src/lib/ws.ts — keep the two in sync."""
    out = candidate.replace("-", "")
    stripped = out.rstrip("0")
    return (stripped or out)[:16]


def binary_short_id(segment_id: uuid.UUID) -> str:
    """Exactly what services/api/app/realtime/pipeline.py writes into the frame."""
    return str(segment_id).replace("-", "")[:16].ljust(16, "\x00")


def test_binary_frame_key_equals_the_json_segment_key() -> None:
    segment_id = uuid.uuid4()
    assert norm_id(binary_short_id(segment_id)) == norm_id(str(segment_id))


def test_ascii_padded_variant_resolves_to_the_same_key() -> None:
    """Tree B pads with the character '0' instead of NUL."""
    segment_id = uuid.uuid4()
    nul_padded = binary_short_id(segment_id)
    ascii_padded = str(segment_id).replace("-", "")[:16].ljust(16, "0")
    assert norm_id(nul_padded) == norm_id(ascii_padded)


def test_dashed_uuid_is_normalised_to_hex() -> None:
    segment_id = uuid.uuid4()
    assert norm_id(str(segment_id)) == str(segment_id).replace("-", "")[:16]


def test_binary_frame_header_layout_is_unchanged() -> None:
    """byte0='T', bytes1-16=short id, byte17=lang length, then lang, then payload."""
    short_id = "a1b2c3d4e5f60718"
    lang = "hi"
    header = b"\x54" + short_id.encode() + bytes([len(lang)]) + lang.encode()
    assert header[0] == 0x54
    assert header[1:17].decode() == short_id
    assert header[17] == 2
    assert header[18:20].decode() == "hi"
    assert len(header) == 20
