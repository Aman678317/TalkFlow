"""Unit tests for chunk manager, retention policy, and privacy cleanup."""
import tempfile
from pathlib import Path
from app.audio.chunk_manager import ChunkManager
from app.audio.quality import AudioQualityAnalyzer
from tests.fixtures.audio_fixtures import generate_speech_like_signal


def test_chunk_creation_and_memory_retention():
    analyzer = AudioQualityAnalyzer()
    pcm = generate_speech_like_signal(100, 16000)
    q = analyzer.analyze(pcm, speech_duration_ms=100)

    mgr = ChunkManager(retention_policy="memory_only", max_in_memory_history=10)
    chunk = mgr.create_chunk(
        session_id="test_sess",
        conversation_id="conv_1",
        speaker_id="spk_1",
        segment_id="seg_001",
        sequence=1,
        start_ms=0,
        end_ms=100,
        pcm_bytes=pcm,
        quality=q,
    )

    assert chunk.segment_id == "seg_001"
    assert chunk.duration_ms == 100
    assert chunk.sequence == 1

    history = mgr.get_session_history("test_sess")
    assert len(history) == 1
    assert history[0].segment_id == "seg_001"


def test_privacy_cleanup_and_temp_file_removal():
    analyzer = AudioQualityAnalyzer()
    pcm = generate_speech_like_signal(100, 16000)
    q = analyzer.analyze(pcm, speech_duration_ms=100)

    with tempfile.TemporaryDirectory() as tmp_dir:
        mgr = ChunkManager(retention_policy="debug_disk", temp_dir=tmp_dir)
        chunk = mgr.create_chunk(
            session_id="privacy_sess",
            conversation_id="conv_1",
            speaker_id="spk_1",
            segment_id="seg_sec",
            sequence=1,
            start_ms=0,
            end_ms=100,
            pcm_bytes=pcm,
            quality=q,
        )

        assert chunk.storage_ref is not None
        chunk_path = Path(chunk.storage_ref)
        assert chunk_path.exists()

        # Execute session cleanup
        mgr.cleanup_session("privacy_sess")

        # Must be wiped
        assert not chunk_path.exists()
        assert len(mgr.get_session_history("privacy_sess")) == 0

