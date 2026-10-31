"""WebSocket streaming endpoint for real-time Language Intelligence."""
from __future__ import annotations

import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.logging import get_logger
from app.models.events import InboundTranscriptEvent
from app.services.language_service import language_service

log = get_logger("api.websocket")
ws_router = APIRouter()


@ws_router.websocket("/api/v1/language/stream/{session_id}")
async def language_streaming_websocket(websocket: WebSocket, session_id: str):
    """Bi-directional streaming WebSocket endpoint for real-time transcript language analysis.
    
    Accepts: Inbound JSON transcript events from Agent 02 or clients:
    - 'transcript.partial' -> returns fast partial language analysis
    - 'transcript.final' -> records speaker history, commits hysteresis, returns finalized analysis
    """
    await websocket.accept()
    log.info(f"WebSocket Language stream opened: session={session_id}")

    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                msg = json.loads(raw_text)
            except Exception:
                await websocket.send_text(json.dumps({"error": "Invalid JSON format"}))
                continue

            event_type = msg.get("type", "transcript.final")
            text = msg.get("text", "")
            speaker_id = msg.get("speaker_id", "user_001")
            conv_id = msg.get("conversation_id", session_id)
            utt_id = msg.get("utterance_id", "utt_ws")
            seg_id = msg.get("segment_id", "seg_ws")
            lang_hint = msg.get("language_hint") or msg.get("language")

            if not text.strip():
                continue

            # Analyze text
            analysis = await language_service.analyze_text(
                text=text,
                session_id=session_id,
                conversation_id=conv_id,
                speaker_id=speaker_id,
                utterance_id=utt_id,
                segment_id=seg_id,
                language_hint=lang_hint,
            )

            # If partial, emit language.analysis.partial
            if event_type == "transcript.partial":
                out_event = {
                    "type": "language.analysis.partial",
                    "session_id": session_id,
                    "speaker_id": speaker_id,
                    "text": text,
                    "primary_language": analysis.primary_language,
                    "confidence": analysis.confidence,
                    "is_multilingual": analysis.is_multilingual,
                    "spans_count": len(analysis.language_spans),
                }
            else:
                # Final analysis event
                out_event = {
                    "type": "language.analysis.final",
                    "session_id": session_id,
                    "conversation_id": conv_id,
                    "speaker_id": speaker_id,
                    "utterance_id": utt_id,
                    "segment_id": seg_id,
                    "original_text": text,
                    "primary_language": analysis.primary_language,
                    "primary_language_script": analysis.primary_language_script,
                    "secondary_languages": analysis.secondary_languages,
                    "is_multilingual": analysis.is_multilingual,
                    "confidence": analysis.confidence,
                    "detection_status": analysis.detection_status,
                    "language_spans": [s.model_dump() for s in analysis.language_spans],
                    "capability_status": analysis.capability_status,
                    "analysis_latency_ms": analysis.analysis_latency_ms,
                }

            await websocket.send_text(json.dumps(out_event))

    except WebSocketDisconnect:
        log.info(f"WebSocket Language stream client disconnected: session={session_id}")
    except Exception as exc:
        log.error(f"WebSocket Language stream error: {exc}", exc_info=True)
        try:
            await websocket.close()
        except Exception:
            pass

