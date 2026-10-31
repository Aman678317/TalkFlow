"""Per-utterance chunk buffer for jitter absorption, reordering, and gap handling."""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple
from app.core.logging import get_logger
from app.models.schemas import AudioChunkIngestRequest

logger = get_logger("jitter.chunk_buffer")


class UtteranceChunkBuffer:
    """Buffers and reassembles incoming audio chunks for a single utterance/language pair.
    
    Ensures in-order chunk emission even if transport or synthesis emits out-of-order.
    Deduplicates repeated chunks and detects missing gaps.
    """

    def __init__(
        self,
        room_id: str,
        segment_id: str,
        target_lang: str,
        speaker_id: str = "speaker_001",
        reorder_wait_ms: float = 60.0,
        max_chunks_per_utterance: int = 128,
    ):
        self.room_id = room_id
        self.segment_id = segment_id
        self.target_lang = target_lang
        self.speaker_id = speaker_id
        self.reorder_wait_ms = reorder_wait_ms
        self.max_chunks = max_chunks_per_utterance

        self.created_at = time.time()
        self.last_chunk_at = self.created_at

        # Storage for received chunks keyed by chunk_index
        self._chunks: Dict[int, AudioChunkIngestRequest] = {}
        self._emitted_indices: set[int] = set()

        self.next_expected_index: int = 0
        self.has_final_chunk: bool = False
        self.final_chunk_index: Optional[int] = None
        self.is_completed: bool = False
        self.is_cancelled: bool = False

    @property
    def key(self) -> str:
        return f"{self.room_id}:{self.segment_id}:{self.target_lang}"

    @property
    def buffered_count(self) -> int:
        return len(self._chunks)

    def add_chunk(self, chunk: AudioChunkIngestRequest) -> Tuple[bool, Optional[str]]:
        """Add an incoming chunk to the reassembly buffer.
        
        Returns:
            (accepted, error_or_drop_reason)
        """
        if self.is_cancelled:
            return False, "utterance_cancelled"
        if self.is_completed:
            return False, "utterance_already_completed"

        idx = chunk.chunk_index

        # Deduplication check
        if idx in self._emitted_indices or idx in self._chunks:
            logger.debug(
                "Duplicate chunk dropped",
                extra={"segment_id": self.segment_id, "chunk_index": idx, "target_lang": self.target_lang}
            )
            return False, "duplicate_chunk"

        if len(self._chunks) >= self.max_chunks:
            logger.warning(
                "Utterance buffer overflow, dropping chunk",
                extra={"segment_id": self.segment_id, "chunk_index": idx}
            )
            return False, "buffer_overflow"

        self._chunks[idx] = chunk
        self.last_chunk_at = time.time()

        if chunk.is_final_chunk:
            self.has_final_chunk = True
            self.final_chunk_index = idx

        return True, None

    def pop_ready_chunks(self, force_gap_skip: bool = False) -> List[AudioChunkIngestRequest]:
        """Pop all contiguous in-order chunks ready for playback.
        
        If force_gap_skip is True (or wait timeout expired), skips a missing chunk index.
        """
        ready: List[AudioChunkIngestRequest] = []
        now = time.time()

        while True:
            if self.next_expected_index in self._chunks:
                chunk = self._chunks.pop(self.next_expected_index)
                self._emitted_indices.add(self.next_expected_index)
                ready.append(chunk)

                if chunk.is_final_chunk or (self.has_final_chunk and self.next_expected_index == self.final_chunk_index):
                    self.is_completed = True
                    break

                self.next_expected_index += 1
            else:
                # Next expected chunk is missing.
                # Check if we should skip the gap due to wait timeout or force flag.
                time_waiting_ms = (now - self.last_chunk_at) * 1000.0
                if (force_gap_skip or time_waiting_ms > self.reorder_wait_ms) and self._chunks:
                    # Look ahead: find smallest index greater than next_expected_index
                    future_indices = [k for k in self._chunks.keys() if k > self.next_expected_index]
                    if future_indices:
                        skipped_index = self.next_expected_index
                        self.next_expected_index = min(future_indices)
                        logger.warning(
                            "Skipping missing chunk gap in jitter buffer",
                            extra={
                                "segment_id": self.segment_id,
                                "skipped_index": skipped_index,
                                "resuming_at_index": self.next_expected_index,
                                "waited_ms": time_waiting_ms,
                            }
                        )
                        continue
                break

        return ready

    def mark_completed(self) -> None:
        """Mark this utterance as fully completed."""
        self.is_completed = True

    def mark_cancelled(self) -> None:
        """Cancel and invalidate this utterance buffer immediately."""
        self.is_cancelled = True
        self._chunks.clear()

