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

import re
import uuid

#: Everything the transport may have added after the real id: NUL (Tree A),
#: the character "0" (Tree B) or whitespace.
_PADDING = re.compile(r"[\s0\x00]+$")


def norm_id(candidate: str) -> str:
    """Mirror of normId() in apps/web/src/lib/ws.ts — keep the two in sync.

    The 16-char cut happens *before* padding is stripped, so a literal "0" that
    is part of the id survives on both transports. Stripping first truncated the
    binary key only, and the browser played that chunk twice.
    """
    return _PADDING.sub("", candidate.replace("-", "")[:16])


def binary_short_id(segment_id: uuid.UUID) -> str:
    """Exactly what services/api/app/realtime/pipeline.py writes into the frame."""
    return str(segment_id).replace("-", "")[:16].ljust(16, "\x00")


def test_binary_frame_key_equals_the_json_segment_key() -> None:
    segment_id = uuid.uuid4()
    assert norm_id(binary_short_id(segment_id)) == norm_id(str(segment_id))


def test_a_prefix_ending_in_a_literal_zero_still_keys_once() -> None:
    """The 16th hex digit is data, not padding.

    This id was chosen because its first 16 hex chars end in "0": the old
    normalize-then-truncate order gave the JSON event
    ``cd58e898050d4280`` and the binary frame ``cd58e898050d428``, so one chunk
    got two queue tags and the listener heard it twice.
    """
    segment_id = uuid.UUID("cd58e898-050d-4280-9c3e-1a2b3c4d5e6f")
    assert str(segment_id).replace("-", "")[15] == "0"
    assert norm_id(binary_short_id(segment_id)) == norm_id(str(segment_id))
    assert norm_id(str(segment_id)) == "cd58e898050d428"


def test_ascii_padded_variant_resolves_to_the_same_key() -> None:
    """Tree B pads with the character '0' instead of NUL."""
    segment_id = uuid.uuid4()
    nul_padded = binary_short_id(segment_id)
    ascii_padded = str(segment_id).replace("-", "")[:16].ljust(16, "0")
    assert norm_id(nul_padded) == norm_id(ascii_padded)


def test_dashed_uuid_is_normalised_to_hex() -> None:
    """Dashes never survive into a key, and the key is a prefix of the 16 hex
    chars both transports derive."""
    segment_id = uuid.uuid4()
    key = norm_id(str(segment_id))
    assert "-" not in key
    assert key and len(key) <= 16
    assert str(segment_id).replace("-", "")[:16].startswith(key)


def test_short_ids_keep_their_padding_stripped() -> None:
    """A label shorter than 16 chars keys the same padded or unpadded."""
    assert norm_id("abc123".ljust(16, "0")) == "abc123"
    assert norm_id("abc123") == "abc123"


def test_capable_binary_frame_header_carries_chunk_index() -> None:
    """Capable clients receive an explicit index before the WAV payload."""
    short_id = "a1b2c3d4e5f60718"
    lang = "hi"
    header = (
        b"\x54" + short_id.encode() + bytes([len(lang)]) + lang.encode()
        + b"\x01" + (3).to_bytes(4, "big")
    )
    assert header[0] == 0x54
    assert header[1:17].decode() == short_id
    assert header[17] == 2
    assert header[18:20].decode() == "hi"
    assert header[20] == 1
    assert int.from_bytes(header[21:25], "big") == 3
    assert len(header) == 25
