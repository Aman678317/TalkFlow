"""Unit tests for PartialManager streaming updates and revision tracking."""
import pytest
from app.providers.fallback.mock_provider import MockSTTProvider
from app.stt.partial_manager import PartialManager
from tests.fixtures.audio_fixtures import generate_tone


@pytest.mark.asyncio
async def test_partial_manager_revisions_and_stale_cancellation():
    provider = MockSTTProvider(default_text="hello world partial")
    manager = PartialManager(provider, partial_interval_ms=100, min_duration_ms=100)

    session_id = "test_sess_1"
    manager.init_utterance(session_id, utterance_id="utt_001", segment_id="seg_001")

    # Add 200ms audio
    audio = generate_tone(440.0, 0.2, 16000)
    manager.append_audio(session_id, audio)

    assert manager.should_emit_partial(session_id, elapsed_ms=150) is True

    # Generate first partial
    evt1 = await manager.generate_partial(
        session_id=session_id,
        conversation_id=session_id,
        speaker_id="speaker_01",
        current_time_ms=150,
    )
    assert evt1 is not None
    assert evt1.revision == 1
    assert evt1.text == "hello world partial"
    assert evt1.is_final is False

    # Second partial should have revision 2
    manager.append_audio(session_id, audio)
    evt2 = await manager.generate_partial(
        session_id=session_id,
        conversation_id=session_id,
        speaker_id="speaker_01",
        current_time_ms=300,
    )
    assert evt2 is not None
    assert evt2.revision == 2

    manager.close_utterance(session_id)

