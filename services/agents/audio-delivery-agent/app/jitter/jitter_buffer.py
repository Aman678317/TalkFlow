"""Global jitter buffer managing active utterance reassembly buffers."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple
from app.core.config import get_settings
from app.core.logging import get_logger
from app.jitter.chunk_buffer import UtteranceChunkBuffer
from app.models.schemas import AudioChunkIngestRequest

logger = get_logger("jitter.buffer_manager")


class JitterBufferManager:
    """Manages active jitter buffers for all concurrent utterances and target languages."""

    def __init__(
        self,
        reorder_wait_ms: Optional[float] = None,
        max_utterance_age_sec: float = 30.0,
        max_active_utterances: int = 100,
    ):
        settings = get_settings()
        self.reorder_wait_ms = reorder_wait_ms or float(settings.jitter_buffer.reorder_wait_ms)
        self.max_utterance_age_sec = max_utterance_age_sec
        self.max_active_utterances = max_active_utterances

        # Map of utterance key -> UtteranceChunkBuffer
        self._buffers: Dict[str, UtteranceChunkBuffer] = {}
        self._lock = asyncio.Lock()

    def _make_key(self, room_id: str, segment_id: str, target_lang: str) -> str:
        return f"{room_id}:{segment_id}:{target_lang}"

    async def ingest_chunk(
        self, chunk: AudioChunkIngestRequest
    ) -> Tuple[bool, Optional[str], List[AudioChunkIngestRequest]]:
        """Ingest chunk into its corresponding jitter buffer.
        
        Returns:
            (accepted, drop_reason, list_of_ordered_ready_chunks)
        """
        async with self._lock:
            key = self._make_key(chunk.session_id, chunk.segment_id, chunk.target_lang)

            if key not in self._buffers:
                if len(self._buffers) >= self.max_active_utterances:
                    # Evict oldest completed or expired buffer
                    self._cleanup_expired_locked()
                    if len(self._buffers) >= self.max_active_utterances:
                        return False, "global_jitter_capacity_exceeded", []

                self._buffers[key] = UtteranceChunkBuffer(
                    room_id=chunk.session_id,
                    segment_id=chunk.segment_id,
                    target_lang=chunk.target_lang,
                    speaker_id=chunk.speaker_id,
                    reorder_wait_ms=self.reorder_wait_ms,
                )

            buffer = self._buffers[key]
            accepted, reason = buffer.add_chunk(chunk)
            if not accepted:
                return False, reason, []

            ready_chunks = buffer.pop_ready_chunks()

            if buffer.is_completed and buffer.buffered_count == 0:
                # Can be removed once consumed
                del self._buffers[key]

            return True, None, ready_chunks

    async def poll_ready_chunks(
        self, room_id: str, segment_id: str, target_lang: str, force_gap_skip: bool = False
    ) -> List[AudioChunkIngestRequest]:
        """Poll for chunks that became ready after timeout wait."""
        async with self._lock:
            key = self._make_key(room_id, segment_id, target_lang)
            if key not in self._buffers:
                return []
            buffer = self._buffers[key]
            ready = buffer.pop_ready_chunks(force_gap_skip=force_gap_skip)
            if buffer.is_completed and buffer.buffered_count == 0:
                del self._buffers[key]
            return ready

    async def cancel_utterance(
        self, room_id: str, segment_id: Optional[str] = None, speaker_id: Optional[str] = None
    ) -> int:
        """Cancel and evict buffers for an utterance, speaker, or room."""
        flushed = 0
        async with self._lock:
            keys_to_remove = []
            for key, buf in self._buffers.items():
                if buf.room_id != room_id:
                    continue
                if segment_id and buf.segment_id != segment_id:
                    continue
                if speaker_id and buf.speaker_id != speaker_id:
                    continue

                flushed += buf.buffered_count
                buf.mark_cancelled()
                keys_to_remove.append(key)

            for key in keys_to_remove:
                del self._buffers[key]

        if flushed > 0:
            logger.info(
                "Flushed chunks on cancellation",
                extra={"room_id": room_id, "segment_id": segment_id, "flushed_chunks": flushed}
            )
        return flushed

    def _cleanup_expired_locked(self) -> None:
        """Purge completed or expired buffers."""
        now = time.time()
        expired_keys = [
            k for k, b in self._buffers.items()
            if b.is_completed or (now - b.last_chunk_at > self.max_utterance_age_sec)
        ]
        for k in expired_keys:
            del self._buffers[k]

    async def get_buffer_stats(self) -> Dict[str, Any]:
        """Get summary statistics of active jitter buffers."""
        async with self._lock:
            total_active = len(self._buffers)
            total_buffered_chunks = sum(b.buffered_count for b in self._buffers.values())
            return {
                "active_utterance_buffers": total_active,
                "total_buffered_chunks": total_buffered_chunks,
                "reorder_wait_ms": self.reorder_wait_ms,
            }

