"""Real-time audio streaming WebSocket endpoint."""
from __future__ import annotations

import asyncio
import json
from typing import Optional
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from app.core.config import settings
from app.core.exceptions import AudioIntelligenceError
from app.core.logging import get_logger
from app.integration.talkflow_adapter import TalkFlowBinaryFrame
from app.services.audio_processor import audio_processor

log = get_logger("websocket")
ws_router = APIRouter()


@ws_router.websocket("/api/v1/audio/stream/{session_id}")
async def audio_stream_endpoint(
    websocket: WebSocket,
    session_id: str,
    conversation_id: Optional[str] = Query(None),
    speaker_id: Optional[str] = Query("user_001"),
    sample_rate: int = Query(16000),
    channels: int = Query(1),
):
    """Real-time bi-directional streaming endpoint for microphone audio frames."""
    await websocket.accept()
    conv_id = conversation_id or session_id
    seq_counter = 0

    # Callback to forward emitted events and binary segments to this connected WebSocket client
    async def handle_pipeline_event(event_dict: dict, pcm_payload: Optional[bytes]):
        try:
            # 1. Send JSON event metadata
            await websocket.send_text(json.dumps(event_dict))
            # 2. If an audio chunk accompanies the event, send as TalkFlow binary frame
            if pcm_payload:
                seg_id = event_dict.get("segment_id", "seg_0")
                binary_frame = TalkFlowBinaryFrame.encode_segment(seg_id, pcm_payload)
                await websocket.send_bytes(binary_frame)

            # 3. Automatically forward finalized audio segment to Agent 02 (STT) and broadcast transcript
            evt_type = event_dict.get("event") or event_dict.get("event_type")
            if evt_type == "audio.segment.final" and pcm_payload:
                async def forward_and_notify():
                    from app.integration.event_publisher import publisher
                    stt_res = await publisher.forward_to_agent02_stt(event_dict, pcm_payload)
                    if stt_res and stt_res.get("text"):
                        try:
                            await websocket.send_text(json.dumps({
                                "version": 1,
                                "event_type": "transcript.final",
                                "segment_id": stt_res.get("segment_id"),
                                "text": stt_res.get("text"),
                                "language": stt_res.get("language_hint"),
                                "confidence": stt_res.get("confidence"),
                                "recognition_latency_ms": stt_res.get("recognition_latency_ms"),
                            }))
                        except Exception:
                            pass
                asyncio.create_task(forward_and_notify())
        except Exception as e:
            log.debug(f"Event delivery to socket skipped (socket closed/busy): {e}")

    try:
        session_state = await audio_processor.session_manager.create_session(
            session_id=session_id,
            conversation_id=conv_id,
            speaker_id=speaker_id or "user_001",
            on_event_callback=handle_pipeline_event,
        )

        # Notify client of successful stream connection
        await websocket.send_text(
            json.dumps({
                "version": 1,
                "event": "session.ready",
                "session_id": session_id,
                "conversation_id": conv_id,
                "speaker_id": speaker_id,
                "canonical_sample_rate": settings.audio.sample_rate,
                "canonical_channels": settings.audio.channels,
            })
        )

        while True:
            try:
                message = await websocket.receive()
            except RuntimeError as re:
                if "disconnect" in str(re).lower():
                    break
                raise

            # Check for WebSocket disconnect message type
            if message.get("type") == "websocket.disconnect":
                break

            # A. Binary audio frame received (raw PCM16 or TalkFlow binary frame)
            if "bytes" in message and message["bytes"]:
                raw_bytes = message["bytes"]
                # Decode TalkFlow binary frame header if present ('O' marker)
                if len(raw_bytes) > 17 and raw_bytes[0] == TalkFlowBinaryFrame.ORIG:
                    _, _, _, pcm_data = TalkFlowBinaryFrame.decode(raw_bytes)
                else:
                    pcm_data = raw_bytes

                seq_counter += 1
                await audio_processor.session_manager.enqueue_frame(
                    session_id=session_id,
                    raw_bytes=pcm_data,
                    sequence=seq_counter,
                    sample_rate=sample_rate,
                    channels=channels,
                    encoding="pcm_s16le",
                )

            # B. Text control frame received
            elif "text" in message and message["text"]:
                try:
                    payload = json.loads(message["text"])
                    evt_type = payload.get("event") or payload.get("type", "")

                    if evt_type == "ping":
                        await websocket.send_text(json.dumps({"event": "pong", "timestamp": payload.get("timestamp")}))

                    elif evt_type == "audio.stopped":
                        log.info(f"Audio stream stopped by client for session {session_id}")
                        break

                    elif evt_type == "audio.frame":
                        # Metadata event specifying sequence for next binary chunk
                        if "sequence" in payload:
                            seq_counter = payload["sequence"]

                except json.JSONDecodeError:
                    pass

    except WebSocketDisconnect:
        log.info(f"WebSocket disconnected for session {session_id}")
    except AudioIntelligenceError as aie:
        log.error(f"Audio intelligence error in session {session_id}: {aie.message}")
        try:
            await websocket.send_text(json.dumps({"event": "error", "message": aie.message}))
        except Exception:
            pass
    except Exception as exc:
        if "disconnect" in str(exc).lower():
            log.info(f"WebSocket client disconnected for session {session_id}")
        else:
            log.error(f"Unexpected streaming exception in session {session_id}: {exc}")
    finally:
        # Gracefully flush and clean up session resources
        await audio_processor.session_manager.terminate_session(session_id)
