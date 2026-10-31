"""Streaming WebSocket endpoint for Agent 06 Text-to-Speech."""
from __future__ import annotations

import json
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.logging import get_logger
from app.models.events import TTSCompletedEvent, TTSFailedEvent
from app.models.schemas import SynthesizeRequest
from app.monitoring.metrics import metrics
from app.services.synthesis_service import SynthesisService

logger = get_logger(__name__)

ws_router = APIRouter(tags=["Streaming TTS"])
service = SynthesisService()


@ws_router.websocket("/api/v1/tts/stream")
async def websocket_tts_stream(websocket: WebSocket) -> None:
    """Real-time streaming synthesis over WebSocket."""
    await websocket.accept()
    logger.info("WebSocket TTS streaming client connected")

    try:
        while True:
            raw_msg = await websocket.receive_text()
            try:
                data = json.loads(raw_msg)
                request = SynthesizeRequest(**data)
            except Exception as e:
                await websocket.send_json({"error": f"Invalid SynthesizeRequest JSON: {e}"})
                continue

            t0 = time.perf_counter()
            total_chunks = 0
            total_duration_ms = 0.0
            first_chunk_latency_ms = 0.0

            try:
                async for chunk_event, binary_frame in service.synthesize_stream(request):
                    if total_chunks == 0:
                        first_chunk_latency_ms = (time.perf_counter() - t0) * 1000.0

                    total_chunks += 1
                    total_duration_ms += chunk_event.duration_ms

                    # Send JSON event metadata
                    await websocket.send_json(chunk_event.model_dump())

                    # Send TalkFlow binary audio frame (0x54 prefix)
                    await websocket.send_bytes(binary_frame)

                # Send completion event
                completed_event = TTSCompletedEvent(
                    session_id=request.session_id,
                    conversation_id=request.conversation_id,
                    speaker_id=request.speaker_id,
                    segment_id=request.segment_id,
                    utterance_id=request.utterance_id or f"utt_{request.segment_id}",
                    translation_id=request.translation_id,
                    target_lang=request.target_language,
                    voice_id=request.requested_voice_id or "auto",
                    provider="talkflow-stream",
                    total_chunks=total_chunks,
                    total_duration_ms=total_duration_ms,
                    generation_latency_ms=(time.perf_counter() - t0) * 1000.0,
                    first_chunk_latency_ms=first_chunk_latency_ms,
                    created_at=time.time(),
                )
                await websocket.send_json(completed_event.model_dump())

                metrics.record_synthesis(
                    provider="stream",
                    language=request.target_language,
                    duration_ms=total_duration_ms,
                    latency_ms=(time.perf_counter() - t0) * 1000.0,
                    chunk_count=total_chunks,
                )

            except Exception as e:
                logger.error("Error during streaming synthesis", extra={"error": str(e)})
                failed_event = TTSFailedEvent(
                    session_id=request.session_id,
                    conversation_id=request.conversation_id,
                    speaker_id=request.speaker_id,
                    segment_id=request.segment_id,
                    target_lang=request.target_language,
                    error_code="STREAM_ERROR",
                    error_message=str(e),
                )
                await websocket.send_json(failed_event.model_dump())

    except WebSocketDisconnect:
        logger.info("WebSocket TTS client disconnected")
    except Exception as e:
        logger.warning(f"WebSocket session terminated: {e}")

