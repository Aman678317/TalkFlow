"""WebSocket streaming endpoint for provisional and final translation events."""
from __future__ import annotations

import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.logging import get_logger
from app.models.schemas import TranslationRequestSchema
from app.services.translation_service import translation_service
from app.translation.partial_manager import partial_manager
from app.translation.streaming import split_stable_prefix

log = get_logger("api.websocket")
ws_router = APIRouter()


@ws_router.websocket("/api/v1/translation/stream/{session_id}")
async def translation_stream_endpoint(websocket: WebSocket, session_id: str) -> None:
    """Streams live partial translations and final translations over WebSocket."""
    await websocket.accept()
    log.info(f"WebSocket translation stream connected: session={session_id}")

    try:
        while True:
            message_text = await websocket.receive_text()
            data = json.loads(message_text)

            msg_type = data.get("type", "translate")
            text = data.get("text", "")
            src = data.get("source_lang", "auto")
            tgt = data.get("target_lang", "en")
            speaker_id = data.get("speaker_id", "user_001")
            is_final = data.get("is_final", False)

            if not text.strip():
                continue

            if not is_final:
                # Provisional streaming pass
                prefix, tail = split_stable_prefix(text, min_prefix=15)
                text_to_translate = prefix if prefix else text
                rev = await partial_manager.get_next_revision(session_id, speaker_id, tgt)

                req = TranslationRequestSchema(
                    text=text_to_translate,
                    source_lang=src,
                    target_lang=tgt,
                    session_id=session_id,
                    speaker_id=speaker_id,
                )
                res = await translation_service.translate_single(req)

                # Check if this partial was superseded while computing
                if not await partial_manager.is_stale(session_id, speaker_id, tgt, rev):
                    await websocket.send_json({
                        "type": "translation.partial",
                        "session_id": session_id,
                        "speaker_id": speaker_id,
                        "source_lang": src,
                        "target_lang": tgt,
                        "revision": rev,
                        "text": res.text,
                        "is_final": False,
                        "provider": res.provider,
                    })

            else:
                # Final translation pass
                req = TranslationRequestSchema(
                    text=text,
                    source_lang=src,
                    target_lang=tgt,
                    session_id=session_id,
                    speaker_id=speaker_id,
                    segment_id=data.get("segment_id"),
                )
                res = await translation_service.translate_single(req)
                await partial_manager.reset(session_id, speaker_id, tgt)

                await websocket.send_json({
                    "type": "translation.final",
                    "session_id": session_id,
                    "speaker_id": speaker_id,
                    "segment_id": data.get("segment_id"),
                    "source_lang": src,
                    "target_lang": tgt,
                    "text": res.text,
                    "is_final": True,
                    "provider": res.provider,
                    "model": res.model,
                    "latency_ms": res.latency_ms,
                    "quality_flags": res.quality_flags,
                })

    except WebSocketDisconnect:
        log.info(f"WebSocket translation client disconnected: session={session_id}")
    except Exception as exc:
        log.error(f"WebSocket translation streaming error: {exc}")
        await websocket.close()

