"""WebSocket handler for real-time streaming translation quality evaluation."""
from __future__ import annotations

import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.logging import get_logger
from app.models.schemas import PartialEvaluationRequestSchema
from app.services.assessment_service import assessment_service

log = get_logger("api.websocket")
ws_router = APIRouter()


@ws_router.websocket("/api/v1/quality/stream/{session_id}")
async def quality_stream_endpoint(websocket: WebSocket, session_id: str) -> None:
    """Streams real-time quality evaluations and safety warnings for streaming translation partials."""
    await websocket.accept()
    log.info(f"WebSocket QA client connected: session={session_id}")

    try:
        while True:
            raw_msg = await websocket.receive_text()
            try:
                data = json.loads(raw_msg)
                src = data.get("source_text", "")
                tgt = data.get("target_text", "")
                src_lang = data.get("source_lang", "hi")
                tgt_lang = data.get("target_lang", "en")
                seg_id = data.get("segment_id", "partial_0")

                req = PartialEvaluationRequestSchema(
                    source_text=src,
                    target_text=tgt,
                    source_lang=src_lang,
                    target_lang=tgt_lang,
                    segment_id=seg_id,
                )

                resp = await assessment_service.evaluate_partial(req)

                await websocket.send_text(
                    json.dumps({
                        "event_type": "quality.assessment.partial",
                        "session_id": session_id,
                        "segment_id": seg_id,
                        "decision": resp.decision.value,
                        "quality_status": resp.quality_status,
                        "overall_score": resp.overall_score,
                        "issues_count": len(resp.issues),
                        "latency_ms": resp.evaluation_latency_ms,
                    })
                )
            except Exception as e:
                await websocket.send_text(json.dumps({"error": f"Invalid payload: {str(e)}"}))

    except WebSocketDisconnect:
        log.info(f"WebSocket QA client disconnected: session={session_id}")
    except Exception as exc:
        log.warning(f"WebSocket QA error: {exc}")

