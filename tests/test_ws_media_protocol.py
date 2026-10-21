"""chan_websocket protocol codec reflects the driver source of the lab build.

Values/frames below are taken verbatim from Asterisk 22.11.0
``channels/chan_websocket.c`` and ``res/ari/resource_channels.c`` so a
regression in the codec is a regression against observed driver behavior.
"""
from __future__ import annotations

import math

import pytest

from app.telephony.media.ws_media_protocol import (
    MAX_CONTROL_MESSAGE_BYTES,
    CadenceTracker,
    ControlMessage,
    FrameChunker,
    FrameSlicer,
    MediaStart,
    WSMediaProtocolError,
    build_command,
    build_json_command,
    parse_media_start,
    rms_linear16,
)

# The exact plain-text MEDIA_START layout emitted by _create_event_MEDIA_START
# (only field ORDER is fixed in the driver; parser must be order-agnostic but
# key-complete).
MEDIA_START_PLAIN = (
    "MEDIA_START connection_id:00000000-0000-0000-0000-000000000000 "
    "channel:WebSocket/pjsip-1001-00000001 "
    "channel_id:talkflow-media-000000000001 "
    "format:slin16 optimal_frame_size:640 ptime:20"
)


def test_media_start_plain_text_parses_all_fields() -> None:
    start = parse_media_start(MEDIA_START_PLAIN)
    assert start.connection_id == "00000000-0000-0000-0000-000000000000"
    assert start.channel == "WebSocket/pjsip-1001-00000001"
    assert start.channel_id == "talkflow-media-000000000001"
    assert start.format == "slin16"
    assert start.optimal_frame_size == 640
    assert start.ptime_ms == 20


def test_media_start_field_order_is_not_load_bearing() -> None:
    reordered = (
        "MEDIA_START ptime:20 format:slin16 optimal_frame_size:640 "
        "channel_id:abc channel:WebSocket/x connection_id:INCOMING"
    )
    start = parse_media_start(reordered)
    assert (start.optimal_frame_size, start.ptime_ms, start.format) == (640, 20, "slin16")


def test_media_start_json_variant_with_channel_variables() -> None:
    raw = (
        '{"event":"MEDIA_START","connection_id":"cid-1","channel":"WebSocket/pjsip-1001-00000002",'
        '"channel_id":"talkflow-media-000000000002","format":"slin16","optimal_frame_size":640,'
        '"ptime":20,"channel_variables":{"TALKFLOW_MEDIA":"1"}}'
    )
    msg = ControlMessage.parse(raw)
    assert isinstance(msg.fields["channel_variables"], str)
    start = parse_media_start(raw)
    assert start.format == "slin16"
    assert start.ptime_ms == 20


def test_missing_media_start_fields_fail_closed() -> None:
    with pytest.raises(WSMediaProtocolError, match="missing fields"):
        parse_media_start("MEDIA_START connection_id:x channel:y")


def test_slIN16_error_messages_name_the_missing_keys() -> None:
    with pytest.raises(WSMediaProtocolError, match="missing fields|MEDIA_START") as err:
        from app.telephony.media.ws_media_protocol import MediaStart as MS

        MS.from_control(
            ControlMessage.parse("MEDIA_START connection_id:x channel:y channel_id:z")
        )
    assert "format" in str(err.value)
    assert "optimal_frame_size" in str(err.value)


def test_non_integer_frame_size_fails_closed() -> None:
    with pytest.raises(WSMediaProtocolError, match="not an integer"):
        parse_media_start(
            "MEDIA_START connection_id:x channel:y channel_id:z format:slin16 "
            "optimal_frame_size:sixforty ptime:20"
        )


def test_control_message_lenient_for_unknown_events() -> None:
    msg = ControlMessage.parse("SOMETHING_ELSE totally free text")
    assert msg.event == "SOMETHING_ELSE"
    assert msg.text == "totally free text"


def test_error_event_keeps_prose() -> None:
    msg = ControlMessage.parse("ERROR not supported in passthrough mode")
    assert msg.event == "ERROR"
    assert msg.text == "not supported in passthrough mode"


def test_dtmf_event_fields() -> None:
    msg = ControlMessage.parse("DTMF_END digit:5 channel_id:talkflow-media-1")
    assert msg.fields == {"digit": "5", "channel_id": "talkflow-media-1"}


def test_build_commands_stay_under_driver_cap() -> None:
    assert build_command("ANSWER") == "ANSWER"
    assert build_command("MARK_MEDIA", "abc-123") == "MARK_MEDIA abc-123"
    payload = build_json_command("SET_MEDIA_DIRECTION", direction="in")
    assert payload == '{"command":"SET_MEDIA_DIRECTION","direction":"in"}'


def test_build_command_enforces_128_byte_cap() -> None:
    long_id = "x" * (MAX_CONTROL_MESSAGE_BYTES)  # 128 + "MARK_MEDIA " prefix overflows
    with pytest.raises(WSMediaProtocolError, match="byte cap"):
        build_command("MARK_MEDIA", long_id)


def test_slicer_assembles_frames_across_chunk_boundaries() -> None:
    slicer = FrameSlicer(640)
    first = bytes(range(256)) * 2  # 512 bytes → incomplete, held as leftover
    second = bytes([9] * 128) + bytes([8] * 640)  # completes frame 1 + full frame 2
    frames = slicer.feed(first)
    assert frames == []
    assert slicer.bytes_buffered == 512
    frames = slicer.feed(second)
    # frame 1 = leftover(512) + front of second message — the driver reassembles
    assert frames == [
        bytes(range(256)) * 2 + bytes([9] * 128),
        bytes([8] * 640),
    ]
    assert slicer.bytes_buffered == 0


def test_slicer_preserves_trailing_partial() -> None:
    slicer = FrameSlicer(100)
    assert slicer.feed(bytes(60)) == []
    assert slicer.feed(bytes(80)) == [bytes(100)]
    assert slicer.bytes_buffered == 40
    assert slicer.flush() == bytes(40)
    assert slicer.flush() is None


def test_slicer_rejects_zero_frame_size() -> None:
    with pytest.raises(ValueError, match="frame_size"):
        FrameSlicer(0)


def test_chunker_splits_and_pads_tail() -> None:
    chunker = FrameChunker(10)
    data = bytes(range(25))
    frames = chunker.chunk(data)
    assert [len(f) for f in frames] == [10, 10, 10]
    assert frames[0] == bytes(range(10))
    assert frames[2] == bytes(range(20, 25)) + bytes([0, 0, 0, 0, 0])
    unpadded = chunker.chunk(data, pad_tail=False)
    assert len(unpadded) == 2


def test_rms_linear16_matches_sine_expectation() -> None:
    # 800 Hz sine over exactly 8 assemblies per 160 samples (complete periods):
    # discrete RMS over whole periods = A/sqrt(2) — zero leakage.
    samples = [
        int(20000 * math.sin(2 * math.pi * 800 * i / 16000)) for i in range(160)
    ]
    import struct

    frame = struct.pack("<160h", *samples)
    rms = rms_linear16(frame)
    assert abs(rms - 20000 / math.sqrt(2)) < 1.0


def test_cadence_tracker_orders_percentiles() -> None:
    tracker = CadenceTracker()
    import struct
    import time

    for _ in range(5):
        tracker.record(struct.pack("<h", 1) * 10)
        time.sleep(0.001)
    assert tracker.frame_count == 5
    assert tracker.byte_count == 100
    assert len(tracker.deltas) == 4
    p50 = tracker.percentile(0.5)
    p95 = tracker.percentile(0.95)
    assert p50 is not None and p95 is not None and p50 <= p95
    tracker.reset_phase()
    assert tracker.last_ts is None


def test_media_start_maybe_ignores_other_events() -> None:
    assert MediaStart.maybe(ControlMessage.parse("MEDIA_XON")) is None
