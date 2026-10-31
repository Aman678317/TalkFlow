"""WebSocket endpoint for real-time streaming speech recognition."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from app.audio.ingestion import AudioIngestionEngine
from app.core.logging import get_logger
from app.integration.talkflow_adapter import TalkFlowAdapter
from app.services.transcription_service import transcription_service

log = get_logger("api.websocket")
ws_router = APIRouter()


@ws_router.websocket("/api/v1/stt/stream/{session_id}")
async def stt_websocket_stream(
    websocket: WebSocket,
    session_id: str,
    speaker_id: str = Query("user_001"),
    conversation_id: str = Query(None),
    language_hint: str = Query(None),
):
    """Real-time bi-directional WebSocket streaming endpoint for Agent 02."""
    await websocket.accept()
    conv_id = conversation_id or session_id

    session = await transcription_service.session_manager.get_or_create_session(
        session_id=session_id,
        speaker_id=speaker_id,
    )

    ingestion = AudioIngestionEngine()
    engine = transcription_service.engine
    partial_mgr = engine.partial_manager

    # Generate utterance ID for this stream
    current_utt_id = f"utt_{uuid.uuid4().hex[:10]}"
    current_seg_id = f"seg_{uuid.uuid4().hex[:10]}"
    partial_mgr.init_utterance(session_id, current_utt_id, current_seg_id)

    stream_start_time = time.perf_counter()
    accumulated_audio = bytearray()

    log.info(f"WebSocket STT stream opened: session={session_id} speaker={speaker_id}")

    try:
        while True:
            message = await websocket.receive()
            msg_type = message.get("type")

            if msg_type == "websocket.disconnect":
                break

            # 1. Handle Binary Audio Frames (50ms chunks)
            if (raw_bytes := message.get("bytes")) is not None:
                try:
                    short_id, pcm16 = ingestion.ingest_binary_frame(raw_bytes)
                except Exception as exc:
                    log.warning(f"Audio frame decode error: {exc}")
                    continue

                accumulated_audio.extend(pcm16)
                partial_mgr.append_audio(session_id, pcm16)

                elapsed_ms = int((time.perf_counter() - stream_start_time) * 1000)

                # Check if we should emit a partial transcript update
                if partial_mgr.should_emit_partial(session_id, elapsed_ms):
                    partial_evt = await partial_mgr.generate_partial(
                        session_id=session_id,
                        conversation_id=conv_id,
                        speaker_id=speaker_id,
                        current_time_ms=elapsed_ms,
                        language_hint=language_hint,
                    )
                    if partial_evt:
                        formatted = TalkFlowAdapter.format_partial_event(partial_evt)
                        await websocket.send_text(json.dumps(formatted))

            # 2. Handle Text Control Messages (e.g. finalize utterance)
            elif (text_data := message.get("text")) is not None:
                try:
                    cmd = json.loads(text_data)
                    action = cmd.get("action")
                    if action == "finalize" and accumulated_audio:
                        final_resp = await engine.transcribe_segment_async(
                            audio_pcm16=bytes(accumulated_audio),
                            session_id=session_id,
                            conversation_id=conv_id,
                            speaker_id=speaker_id,
                            utterance_id=current_utt_id,
                            segment_id=current_seg_id,
                            seq=cmd.get("seq", 1),
                            start_ms=0,
                            sample_rate=16000,
                            language_hint=language_hint,
                            word_timestamps=True,
                        )
                        final_evt = engine.finalizer.to_event(final_resp, seq=cmd.get("seq", 1))
                        formatted = TalkFlowAdapter.format_final_event(final_evt)
                        await websocket.send_text(json.dumps(formatted))

                        # Automatically forward finalized transcript to Agent 03
                        if final_resp.text.strip():
                            from app.integration.agent03_publisher import publisher_to_agent03
                            asyncio.create_task(publisher_to_agent03.forward_transcript_to_agent03(final_resp))

                        # Reset for next utterance
                        accumulated_audio.clear()
                        current_utt_id = f"utt_{uuid.uuid4().hex[:10]}"
                        current_seg_id = f"seg_{uuid.uuid4().hex[:10]}"
                        partial_mgr.init_utterance(session_id, current_utt_id, current_seg_id)

                    elif action == "ping":
                        await websocket.send_text(json.dumps({"type": "pong", "timestamp": time.time()}))
                except Exception as exc:
                    log.warning(f"Control message error: {exc}")

    except (WebSocketDisconnect, RuntimeError):
        log.info(f"WebSocket STT client disconnected: {session_id}")
    finally:
        partial_mgr.close_utterance(session_id)
        await transcription_service.session_manager.remove_session(session_id)

