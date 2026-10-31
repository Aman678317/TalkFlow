"""Core Delivery Orchestrator coordinating all audio delivery pipeline stages."""
from __future__ import annotations

import base64
import time
from typing import Any, Dict, List, Optional
from app.cancellation.barge_in_manager import BargeInManager
from app.core.exceptions import AudioDeliveryError, ProvenanceValidationError
from app.core.logging import get_logger
from app.jitter.jitter_buffer import JitterBufferManager
from app.models.delivery_models import ParticipantRoute
from app.models.events import (
    AudioDroppedEvent,
    AudioPlaybackCompletedEvent,
    AudioPublishedEvent,
    AudioQueuedEvent,
)
from app.models.schemas import AudioChunkIngestRequest, IngestionResponse, UtteranceFinalizeRequest
from app.routing.fanout_engine import FanoutEngine
from app.routing.participant_router import ParticipantRouter
from app.sync.scheduler import PlaybackScheduler
from app.sync.stale_detector import StaleDetector
from app.sync.timeline import TurnTimelineTracker
from app.transport.binary_wire import encode_talkflow_binary_frame
from app.transport.ducking_mixer import DuckingMixer
from app.transport.livekit_adapter import LiveKitAdapter
from app.transport.websocket_broadcaster import WebSocketBroadcaster

logger = get_logger("services.orchestrator")


class AudioDeliveryOrchestrator:
    """Central orchestrator for Agent 07 Audio Synchronization & Delivery."""

    def __init__(self):
        self.router = ParticipantRouter()
        self.jitter_buffer = JitterBufferManager()
        self.timeline = TurnTimelineTracker()
        self.stale_detector = StaleDetector(self.timeline)
        self.scheduler = PlaybackScheduler()
        self.fanout = FanoutEngine(self.router)
        self.livekit = LiveKitAdapter()
        self.broadcaster = WebSocketBroadcaster()
        self.ducking = DuckingMixer()
        self.barge_in = BargeInManager(self.jitter_buffer, self.broadcaster)

        # Performance and audit counters
        self.total_ingested_chunks = 0
        self.total_delivered_chunks = 0
        self.total_dropped_chunks = 0
        self.total_fanout_deliveries = 0

    async def ingest_audio_chunk(self, chunk: AudioChunkIngestRequest) -> IngestionResponse:
        """Process incoming audio chunk through full synchronization and delivery pipeline."""
        start_t = time.time()
        self.total_ingested_chunks += 1

        # 1. Provenance and synthetic marker validation
        if not chunk.synthetic or chunk.audio_origin != "synthetic_tts":
            logger.warning(
                "Rejected audio chunk with non-synthetic provenance",
                extra={"segment_id": chunk.segment_id, "audio_origin": chunk.audio_origin}
            )
            self.total_dropped_chunks += 1
            raise ProvenanceValidationError(
                "Audio chunk must be marked synthetic with origin 'synthetic_tts' to prevent feedback loops."
            )

        # 2. Check conversational staleness
        is_stale, stale_reason = self.stale_detector.is_chunk_stale(chunk)
        if is_stale:
            self.total_dropped_chunks += 1
            logger.info(
                "Dropped stale audio chunk",
                extra={"segment_id": chunk.segment_id, "chunk_index": chunk.chunk_index, "reason": stale_reason}
            )
            return IngestionResponse(
                status="dropped",
                segment_id=chunk.segment_id,
                chunk_index=chunk.chunk_index,
                target_lang=chunk.target_lang,
                action_taken="dropped_stale",
                details=stale_reason,
                latency_ms=(time.time() - start_t) * 1000.0,
            )

        # 3. Register turn start on timeline
        self.timeline.record_turn_start(
            room_id=chunk.session_id,
            speaker_id=chunk.speaker_id,
            seq=chunk.seq,
            start_wall_ms=chunk.start_wall_ms,
        )

        # 4. Ingest into Jitter Buffer for reordering and gap handling
        accepted, drop_reason, ready_chunks = await self.jitter_buffer.ingest_chunk(chunk)
        if not accepted:
            self.total_dropped_chunks += 1
            return IngestionResponse(
                status="dropped",
                segment_id=chunk.segment_id,
                chunk_index=chunk.chunk_index,
                target_lang=chunk.target_lang,
                action_taken="dropped_by_jitter_buffer",
                details=drop_reason,
                latency_ms=(time.time() - start_t) * 1000.0,
            )

        # If chunk is stored in jitter buffer waiting for previous chunks
        if not ready_chunks:
            return IngestionResponse(
                status="queued",
                segment_id=chunk.segment_id,
                chunk_index=chunk.chunk_index,
                target_lang=chunk.target_lang,
                action_taken="buffered_for_reordering",
                latency_ms=(time.time() - start_t) * 1000.0,
            )

        # 5. Dispatch ready in-order chunks
        dispatched_count = 0
        total_recipients = 0

        for r_chunk in ready_chunks:
            # Pacing and playout scheduling
            scheduled_ms = self.scheduler.schedule_chunk(r_chunk)

            # Fan-out recipient resolution
            recipients = self.fanout.resolve_fanout_targets(r_chunk)
            total_recipients += len(recipients)

            # Decode raw audio bytes from base64 if present
            audio_bytes = b""
            if r_chunk.audio_base64:
                try:
                    audio_bytes = base64.b64decode(r_chunk.audio_base64)
                except Exception as exc:
                    logger.error("Failed to decode audio_base64", extra={"error": str(exc)})

            # Deliver over transports
            # A. LiveKit synthetic track
            await self.livekit.publish_chunk(
                room_id=r_chunk.session_id,
                target_lang=r_chunk.target_lang,
                audio_bytes=audio_bytes,
                sample_rate=r_chunk.sample_rate,
                seq=r_chunk.seq,
                chunk_index=r_chunk.chunk_index,
            )

            # B. WebSocket binary frame and JSON event to eligible listeners
            if recipients and audio_bytes:
                for rec in recipients:
                    # Construct TalkFlow binary wire frame
                    bin_frame = encode_talkflow_binary_frame(
                        segment_id=r_chunk.segment_id,
                        target_lang=r_chunk.target_lang,
                        chunk_index=r_chunk.chunk_index,
                        audio_bytes=audio_bytes,
                        supports_tts_chunk_index=rec.supports_tts_chunk_index,
                    )
                    await self.broadcaster.send_binary(r_chunk.session_id, rec.participant_id, bin_frame)

                    # JSON event delivery
                    json_event = {
                        "type": "tts.chunk",
                        "segment_id": r_chunk.segment_id,
                        "utterance_id": r_chunk.utterance_id or r_chunk.segment_id,
                        "seq": r_chunk.seq,
                        "target_lang": r_chunk.target_lang,
                        "chunk_index": r_chunk.chunk_index,
                        "audio_base64": r_chunk.audio_base64,
                        "format": r_chunk.format,
                        "sample_rate": r_chunk.sample_rate,
                        "created_at": r_chunk.created_at,
                    }
                    await self.broadcaster.send_json(r_chunk.session_id, rec.participant_id, json_event)
                    self.total_fanout_deliveries += 1

            dispatched_count += 1
            self.total_delivered_chunks += 1

        latency_ms = (time.time() - start_t) * 1000.0

        return IngestionResponse(
            status="published" if total_recipients > 0 else "scheduled",
            segment_id=chunk.segment_id,
            chunk_index=chunk.chunk_index,
            target_lang=chunk.target_lang,
            action_taken=f"dispatched_{dispatched_count}_ready_chunks",
            recipients_count=total_recipients,
            latency_ms=latency_ms,
        )

    async def finalize_utterance(self, req: UtteranceFinalizeRequest) -> Dict[str, Any]:
        """Handle synthesis completion notification."""
        # Poll any remaining chunks in buffer with force gap skip
        ready_chunks = await self.jitter_buffer.poll_ready_chunks(
            room_id=req.session_id,
            segment_id=req.segment_id,
            target_lang=req.target_lang,
            force_gap_skip=True,
        )

        # Reset scheduler for this utterance
        self.scheduler.reset_utterance(req.session_id, req.segment_id, req.target_lang)

        # Notify participants of completion
        recipients = self.router.get_recipients(req.session_id, req.target_lang, req.speaker_id)
        if recipients:
            comp_msg = {
                "type": "tts.completed",
                "segment_id": req.segment_id,
                "utterance_id": req.utterance_id or req.segment_id,
                "target_lang": req.target_lang,
                "total_chunks": req.total_chunks,
                "total_duration_ms": req.total_duration_ms,
            }
            rec_ids = [p.participant_id for p in recipients]
            await self.broadcaster.broadcast_json(req.session_id, rec_ids, comp_msg)

        logger.info(
            "Finalized audio delivery for utterance",
            extra={"segment_id": req.segment_id, "target_lang": req.target_lang, "flushed_ready": len(ready_chunks)}
        )

        return {
            "status": "completed",
            "segment_id": req.segment_id,
            "target_lang": req.target_lang,
            "remaining_flushed": len(ready_chunks),
        }

    async def get_stats(self) -> Dict[str, Any]:
        """Aggregate operational statistics."""
        buf_stats = await self.jitter_buffer.get_buffer_stats()
        return {
            "total_ingested_chunks": self.total_ingested_chunks,
            "total_delivered_chunks": self.total_delivered_chunks,
            "total_dropped_chunks": self.total_dropped_chunks,
            "total_fanout_deliveries": self.total_fanout_deliveries,
            "active_rooms_count": len(self.router.list_all_rooms()),
            "connected_websockets": self.broadcaster.get_connected_count(),
            "jitter_buffer": buf_stats,
        }

