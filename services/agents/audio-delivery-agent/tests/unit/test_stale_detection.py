"""Unit tests for StaleDetector and TurnTimelineTracker."""
from __future__ import annotations

import time
import pytest
from app.models.schemas import AudioChunkIngestRequest
from app.sync.stale_detector import StaleDetector
from app.sync.timeline import TurnTimelineTracker


def test_stale_chunk_detection():
    timeline = TurnTimelineTracker()
    detector = StaleDetector(timeline=timeline, max_stale_delay_ms=1000.0)

    # 1. Fresh chunk
    fresh_chunk = AudioChunkIngestRequest(
        session_id="room_fresh",
        conversation_id="room_fresh",
        speaker_id="speaker_001",
        segment_id="seg_001",
        target_lang="en",
        seq=1,
        start_wall_ms=time.time() * 1000.0,
        synthetic=True,
        audio_origin="synthetic_tts",
    )
    is_stale, reason = detector.is_chunk_stale(fresh_chunk)
    assert is_stale is False

    # 2. Stale chunk lagging by 2500ms
    stale_chunk = AudioChunkIngestRequest(
        session_id="room_fresh",
        conversation_id="room_fresh",
        speaker_id="speaker_001",
        segment_id="seg_old",
        target_lang="en",
        seq=1,
        start_wall_ms=(time.time() - 2.5) * 1000.0,  # 2500ms ago
        synthetic=True,
        audio_origin="synthetic_tts",
    )
    is_stale, reason = detector.is_chunk_stale(stale_chunk)
    assert is_stale is True
    assert "turn_start_wall_age_exceeded" in reason


def test_superseded_sequence_detection():
    timeline = TurnTimelineTracker()
    detector = StaleDetector(timeline=timeline, max_stale_delay_ms=2000.0)

    # Register turn seq 5 on timeline
    timeline.record_turn_start(room_id="room_seq", speaker_id="speaker_001", seq=5)

    # Older chunk from seq 3 arrives late
    late_seq_chunk = AudioChunkIngestRequest(
        session_id="room_seq",
        conversation_id="room_seq",
        speaker_id="speaker_001",
        segment_id="seg_late",
        target_lang="hi",
        seq=3,
        synthetic=True,
        audio_origin="synthetic_tts",
    )
    is_stale, reason = detector.is_chunk_stale(late_seq_chunk)
    assert is_stale is True
    assert "superseded_by_newer_sequence" in reason

