"""WebSocket endpoints for real-time audio delivery streaming."""
from __future__ import annotations

import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.api.routes import orchestrator
from app.core.logging import get_logger

logger = get_logger("api.websocket")
ws_router = APIRouter()


@ws_router.websocket("/ws/audio/delivery/{room_id}/{participant_id}")
async def websocket_audio_delivery_endpoint(
    websocket: WebSocket, room_id: str, participant_id: str
):
    """Real-time duplex WebSocket for binary audio frames and control signalling."""
    await orchestrator.broadcaster.connect(room_id, participant_id, websocket)

    try:
        while True:
            # Receive client events (ping, preferences update, barge-in interrupt)
            message = await websocket.receive()

            if "text" in message and message["text"]:
                try:
                    payload = json.loads(message["text"])
                    ev_type = payload.get("type", "")

                    if ev_type == "ping":
                        await websocket.send_text(json.dumps({"type": "pong", "time": payload.get("time")}))
                    elif ev_type in ("playback.interrupt", "playback_interrupt"):
                        await orchestrator.barge_in.handle_interruption(
                            room_id=room_id,
                            speaker_id=participant_id,
                            reason="client_playback_interrupt",
                        )
                    elif ev_type == "preferences.update":
                        orchestrator.router.update_preferences(
                            room_id=room_id,
                            participant_id=participant_id,
                            hear_lang=payload.get("hear_lang"),
                            playback_mode=payload.get("playback_mode"),
                        )
                except Exception as parse_err:
                    logger.warning("Error parsing client text event", extra={"error": str(parse_err)})

            elif "bytes" in message and message["bytes"]:
                # If participant sends client audio, log or route
                logger.debug("Received client binary frame", extra={"bytes_len": len(message["bytes"])})

    except WebSocketDisconnect:
        logger.info(
            "WebSocket client disconnected gracefully",
            extra={"room_id": room_id, "participant_id": participant_id}
        )
    except Exception as exc:
        logger.warning(
            "WebSocket connection encountered error",
            extra={"room_id": room_id, "participant_id": participant_id, "error": str(exc)}
        )
    finally:
        await orchestrator.broadcaster.disconnect(room_id, participant_id)

