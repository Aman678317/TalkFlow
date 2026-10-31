"""Unit tests for FinalizerEngine and idempotency."""
from app.providers.fallback.mock_provider import MockSTTProvider
from app.stt.finalizer import FinalizerEngine
from tests.fixtures.audio_fixtures import generate_tone


def test_finalizer_transcribes_and_converts_timestamps():
    provider = MockSTTProvider(default_text="hello everyone today")
    finalizer = FinalizerEngine(provider)

    audio = generate_tone(440.0, 0.5, 16000)
    resp = finalizer.finalize(
        audio_pcm16=audio,
        session_id="sess_01",
        conversation_id="conv_01",
        speaker_id="user_01",
        utterance_id="utt_01",
        segment_id="seg_01",
        seq=1,
        start_ms=1000,
        sample_rate=16000,
    )

    assert resp.is_final is True
    assert resp.text == "hello everyone today"
    assert resp.segment_id == "seg_01"
    assert len(resp.segments) >= 1
    # Check that segment timestamp was shifted by start_ms=1000
    assert resp.segments[0].start_ms == 1000

    # Test idempotency detection
    assert finalizer.is_finalized("seg_01") is True

    # Convert to TalkFlow event envelope
    evt = finalizer.to_event(resp, seq=1)
    assert evt.type == "transcript.final"
    assert evt.segment_id == "seg_01"
    assert evt.is_final is True

