"""REST API routes for Agent 07 Audio Delivery Agent."""
from __future__ import annotations

import time
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Response
from app.agents.brain import brain
from app.core.exceptions import AudioDeliveryError, RoomIsolatedError
from app.core.logging import get_logger
from app.models.delivery_models import ParticipantRoute
from app.models.schemas import (
    AudioChunkIngestRequest,
    BrainQueryRequest,
    BrainQueryResponse,
    CancellationRequest,
    IngestionResponse,
    RegisterParticipantRequest,
    RoomStatusResponse,
    UpdatePreferencesRequest,
    UtteranceFinalizeRequest,
)
from app.monitoring.metrics import metrics
from app.services.delivery_orchestrator import AudioDeliveryOrchestrator

logger = get_logger("api.routes")
router = APIRouter()

# Global orchestrator instance
orchestrator = AudioDeliveryOrchestrator()


@router.post("/delivery/chunks", response_model=IngestionResponse)
@router.post("/audio/sync/chunk", response_model=IngestionResponse)
async def ingest_audio_chunk(request: AudioChunkIngestRequest) -> IngestionResponse:
    """Ingest, buffer, synchronize, and fan out an audio chunk from Agent 06."""
    try:
        metrics.record_ingest()
        res = await orchestrator.ingest_audio_chunk(request)
        if res.status == "published":
            metrics.record_delivery()
            metrics.record_fanout(res.recipients_count)
        elif res.status == "dropped":
            metrics.record_drop(res.details or "unknown")
        metrics.record_latency(res.latency_ms)
        return res
    except AudioDeliveryError as err:
        logger.error("Audio delivery error during ingestion", extra={"error": str(err)})
        metrics.record_drop("audio_delivery_error")
        raise HTTPException(status_code=400, detail=str(err))
    except Exception as exc:
        logger.exception("Unexpected error ingesting audio chunk")
        metrics.record_drop("internal_server_error")
        raise HTTPException(status_code=500, detail=f"Internal ingestion error: {exc}")


@router.post("/audio/sync/started")
async def start_audio_sync(request: Dict[str, Any]) -> Dict[str, Any]:
    """Notify start of speech synthesis for an utterance (from Agent 06)."""
    room_id = request.get("session_id") or request.get("conversation_id", "default_room")
    speaker_id = request.get("speaker_id", "speaker_001")
    seq = request.get("seq", 1)

    orchestrator.timeline.record_turn_start(
        room_id=room_id,
        speaker_id=speaker_id,
        seq=seq,
    )
    orchestrator.router.get_or_create_room(room_id)
    return {"status": "started", "session_id": room_id, "speaker_id": speaker_id}


@router.post("/delivery/finalize")
@router.post("/audio/sync/completed")
async def finalize_utterance(request: UtteranceFinalizeRequest) -> Dict[str, Any]:
    """Notify completion of speech synthesis for an utterance."""
    try:
        return await orchestrator.finalize_utterance(request)
    except Exception as exc:
        logger.exception("Failed to finalize utterance")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/delivery/cancel")
@router.post("/audio/sync/cancel")
async def cancel_playback(request: CancellationRequest) -> Dict[str, Any]:
    """Execute barge-in interruption, flush buffers, and broadcast cancellation."""
    try:
        metrics.record_barge_in()
        return await orchestrator.barge_in.handle_interruption(
            room_id=request.room_id,
            session_id=request.session_id,
            speaker_id=request.speaker_id,
            segment_id=request.segment_id,
            reason=request.reason,
        )
    except Exception as exc:
        logger.exception("Failed to execute barge-in flush")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/delivery/stats")
async def get_delivery_stats() -> Dict[str, Any]:
    """Retrieve operational statistics of the delivery agent."""
    return await orchestrator.get_stats()


@router.post("/rooms/participants")
async def register_participant(request: RegisterParticipantRequest) -> Dict[str, Any]:
    """Register or update a participant and their language/audio preferences."""
    try:
        route = ParticipantRoute(
            participant_id=request.participant_id,
            room_id=request.room_id,
            tenant_id=request.tenant_id,
            display_name=request.display_name,
            hear_lang=request.hear_lang,
            speaking_lang=request.speaking_lang,
            playback_mode=request.playback_mode,
            translation_audio_enabled=request.translation_audio_enabled,
            original_audio_enabled=request.original_audio_enabled,
            captions_enabled=request.captions_enabled,
            supports_tts_chunk_index=request.supports_tts_chunk_index,
        )
        room = orchestrator.router.register_participant(route)
        return {
            "status": "registered",
            "participant_id": request.participant_id,
            "room_id": request.room_id,
            "total_participants": len(room.participants),
        }
    except RoomIsolatedError as rie:
        raise HTTPException(status_code=403, detail=str(rie))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/rooms/{room_id}", response_model=RoomStatusResponse)
async def get_room(room_id: str) -> RoomStatusResponse:
    """Get active session details and participants for a room."""
    room = orchestrator.router.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail=f"Room {room_id} not found")

    return RoomStatusResponse(
        room_id=room.room_id,
        tenant_id=room.tenant_id,
        participant_count=len(room.participants),
        active_tracks=list(room.active_tracks.keys()),
        participants=[p.model_dump() for p in room.participants.values()],
        active_utterances=list(room.active_utterance_ids),
    )


@router.patch("/rooms/{room_id}/participants/{participant_id}")
async def update_participant_preferences(
    room_id: str, participant_id: str, request: UpdatePreferencesRequest
) -> Dict[str, Any]:
    """Update dynamic audio preferences (e.g. language or playback mode)."""
    p = orchestrator.router.update_preferences(
        room_id=room_id,
        participant_id=participant_id,
        hear_lang=request.hear_lang,
        playback_mode=request.playback_mode,
        translation_audio_enabled=request.translation_audio_enabled,
        original_audio_enabled=request.original_audio_enabled,
        captions_enabled=request.captions_enabled,
    )
    if not p:
        raise HTTPException(status_code=404, detail="Participant not found")
    return {"status": "updated", "participant": p.model_dump()}


@router.delete("/rooms/{room_id}/participants/{participant_id}")
async def unregister_participant(room_id: str, participant_id: str) -> Dict[str, Any]:
    """Unregister a participant from a room."""
    orchestrator.router.unregister_participant(room_id, participant_id)
    return {"status": "unregistered", "participant_id": participant_id}


@router.post("/brain/query", response_model=BrainQueryResponse)
async def query_brain(request: BrainQueryRequest) -> BrainQueryResponse:
    """Consult Agent 07 diagnostic brain for delivery and synchronization analysis."""
    return await brain.query(request.query, request.context)
