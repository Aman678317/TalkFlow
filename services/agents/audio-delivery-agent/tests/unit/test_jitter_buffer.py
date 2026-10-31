"""Unit tests for JitterBuffer and UtteranceChunkBuffer."""
from __future__ import annotations

import pytest
from app.jitter.chunk_buffer import UtteranceChunkBuffer
from app.jitter.jitter_buffer import JitterBufferManager
from app.models.schemas import AudioChunkIngestRequest


def _make_dummy_chunk(chunk_index: int, is_final: bool = False) -> AudioChunkIngestRequest:
    return AudioChunkIngestRequest(
        session_id="room_test",
        conversation_id="room_test",
        speaker_id="speaker_001",
        segment_id="seg_001",
        target_lang="mr",
        chunk_index=chunk_index,
        is_final_chunk=is_final,
        synthetic=True,
        audio_origin="synthetic_tts",
        audio_base64="AAAA",
    )


def test_chunk_reordering():
    """Verify that chunks arriving out of order (1, 2, 0) are emitted contiguously (0, 1, 2)."""
    buf = UtteranceChunkBuffer(room_id="room_test", segment_id="seg_001", target_lang="mr")

    c0 = _make_dummy_chunk(0)
    c1 = _make_dummy_chunk(1)
    c2 = _make_dummy_chunk(2, is_final=True)

    # Ingest 1 and 2 first
    acc1, _ = buf.add_chunk(c1)
    acc2, _ = buf.add_chunk(c2)
    assert acc1 and acc2
    assert buf.buffered_count == 2

    # Since 0 is missing, ready chunks should be empty
    ready = buf.pop_ready_chunks()
    assert len(ready) == 0

    # Now ingest 0
    acc0, _ = buf.add_chunk(c0)
    assert acc0

    # Pop ready chunks: should yield 0, 1, 2 in order
    ready = buf.pop_ready_chunks()
    assert len(ready) == 3
    assert [c.chunk_index for c in ready] == [0, 1, 2]
    assert buf.is_completed is True


def test_duplicate_chunk_detection():
    """Verify that duplicate chunks are rejected."""
    buf = UtteranceChunkBuffer(room_id="room_test", segment_id="seg_001", target_lang="mr")
    c0 = _make_dummy_chunk(0)

    acc, err = buf.add_chunk(c0)
    assert acc is True
    assert err is None

    # Re-send chunk 0
    acc2, err2 = buf.add_chunk(c0)
    assert acc2 is False
    assert err2 == "duplicate_chunk"


@pytest.mark.asyncio
async def test_jitter_buffer_manager():
    """Verify JitterBufferManager ingestion and multi-chunk lifecycle."""
    mgr = JitterBufferManager()

    c0 = _make_dummy_chunk(0, is_final=False)
    c1 = _make_dummy_chunk(1, is_final=True)

    acc0, err0, ready0 = await mgr.ingest_chunk(c0)
    assert acc0 is True
    assert len(ready0) == 1
    assert ready0[0].chunk_index == 0

    acc1, err1, ready1 = await mgr.ingest_chunk(c1)
    assert acc1 is True
    assert len(ready1) == 1
    assert ready1[0].chunk_index == 1
    assert ready1[0].is_final_chunk is True

