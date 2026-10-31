"""Integration tests for TalkFlow wire format decoding and event compatibility."""
from app.integration.talkflow_adapter import TalkFlowAdapter, TalkFlowBinaryFrame
from tests.fixtures.audio_fixtures import generate_speech_like_signal


def test_talkflow_binary_frame_roundtrip():
    short_id = "seg_abc123456789"
    original_pcm = generate_speech_like_signal(50, 16000)

    # Encode
    encoded = TalkFlowBinaryFrame.encode_segment(short_id, original_pcm)
    assert len(encoded) == 1 + 16 + len(original_pcm)
    assert encoded[0] == TalkFlowBinaryFrame.ORIG

    # Decode
    kind, decoded_id, lang, payload = TalkFlowBinaryFrame.decode(encoded)
    assert kind == "original"
    assert decoded_id == short_id
    assert lang == ""
    assert payload == original_pcm


def test_talkflow_contract_event_formatting():
    event = TalkFlowAdapter.format_output_event(
        event_type="audio.segment.final",
        session_id="meeting_123",
        conversation_id="meeting_123",
        speaker_id="user_001",
        segment_id="segment_001",
        sequence=101,
        start_ms=1000,
        end_ms=4500,
        duration_ms=3500,
        quality_dict={
            "speech_detected": True,
            "noise_detected": False,
            "clipping_detected": False,
            "quality_status": "good",
        },
        status="final",
    )

    assert event["event"] == "audio.segment.final"
    assert event["agent"] == "audio_intelligence"
    assert event["session_id"] == "meeting_123"
    assert event["conversation_id"] == "meeting_123"
    assert event["speaker_id"] == "user_001"
    assert event["segment_id"] == "segment_001"
    assert event["sequence"] == 101
    assert event["start_ms"] == 1000
    assert event["end_ms"] == 4500
    assert event["duration_ms"] == 3500
    assert event["sample_rate"] == 16000
    assert event["channels"] == 1
    assert event["encoding"] == "pcm_s16le"
    assert event["status"] == "final"
    assert event["quality"]["quality_status"] == "good"

