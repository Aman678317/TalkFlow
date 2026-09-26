"""WebSocket realtime endpoint (PDD §11, §14, §38).

Auth: short-lived session ticket (minted by REST /voice/sessions or meeting
join) — the browser never holds long-lived inference credentials.

Transport:
- JSON text frames = protocol events
- binary frames    = raw PCM16 mono audio (after audio.start), lowest overhead

Reconnect: client sends session.resume {last_sequence}; server replays
buffered events with sequence > last_sequence (idempotent by sequence).
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import time
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select

from app import metrics as met
from app.config import settings
from app.db import models as M
from app.db.session import db_session
from app.errors import AuthenticationError
from app.realtime import pipeline as pl
from app.realtime.protocol import ClientEventType, ServerEventType, parse_client_event
from app.realtime.session_manager import RtParticipant, manager
from app.security import verify_session_ticket
from app.services import chat_service

log = logging.getLogger("app.realtime.ws")

router = APIRouter()

HEARTBEAT_INTERVAL_S = 25
RECEIVE_TIMEOUT_S = 90


@router.websocket("/ws/realtime")
async def realtime_ws(
    ws: WebSocket,
    ticket: str = Query(default=""),
    meeting_id: str = Query(default=""),
):
    # ---- authenticate via ticket --------------------------------------- #
    try:
        session_id_hint, participant_id = _auth(ticket, meeting_id)
    except AuthenticationError as e:
        await ws.close(code=4401, reason=e.message)
        return

    async with db_session() as db:
        participant = await db.get(M.Participant, participant_id)
        if participant is None:
            await ws.close(code=4404, reason="participant not found")
            return
        meeting = await db.get(M.Meeting, participant.meeting_id)
        if meeting is None or meeting.status not in ("scheduled", "live"):
            await ws.close(code=4410, reason="meeting not joinable")
            return
        pref = (await db.execute(select(M.ParticipantPreference).where(
            M.ParticipantPreference.participant_id == participant.id))).scalars().first()
        meeting_id_uuid = meeting.id
        org_id = meeting.org_id
        room_name = meeting.room_name
        mode = meeting.mode
        db_seq = int((await db.execute(
            select(func.coalesce(func.max(M.TranscriptSegment.seq), 0))
            .where(M.TranscriptSegment.meeting_id == meeting.id))).scalar() or 0)
        p_data = dict(
            participant_id=participant.id, user_id=participant.user_id,
            display_name=participant.display_name,
            speak_lang=pref.speak_lang if pref else "auto",
            hear_lang=pref.hear_lang if pref else "en",
            audio_mode=pref.audio_mode if pref else "translated",
            captions_enabled=pref.captions_enabled if pref else True,
        )

    await ws.accept()
    met.WS_CONNECTIONS.inc()

    # ---- session bootstrap ---------------------------------------------- #
    session = manager.get_session_for_meeting(meeting_id_uuid)
    resumed = False
    if session is None:
        session = await manager.create_session(meeting_id_uuid, org_id, room_name,
                                               mode, db_seq_start=db_seq)
        pl.get_pipeline(session)
    else:
        resumed = True

    rp = RtParticipant(**p_data)
    existing = session.participants.get(str(rp.participant_id))
    if existing is not None:
        rp.last_seq_seen = existing.last_seq_seen  # preserve resume position
    manager.add_participant(session, rp)
    manager.attach_ws(session, rp.participant_id, ws)
    pl.get_pipeline(session).start_speaker(rp)

    await manager.send_to(rp, session, ServerEventType.SESSION_CREATED, {
        "meeting_id": str(meeting_id_uuid),
        "room_name": room_name,
        "mode": mode,
        "participant_id": str(rp.participant_id),
        "display_name": rp.display_name,
        "speak_lang": rp.speak_lang,
        "hear_lang": rp.hear_lang,
        "audio_mode": rp.audio_mode,
        "protocol_version": 1,
        "server_sequence": session.sequence,
        "ai": {"translation": "active", "dev_mode": _dev_flags()},
        "participants": [_participant_snapshot(k, v)
                         for k, v in session.participants.items()],
    }, sequenced=False)

    if resumed:
        await manager.send_to(rp, session, ServerEventType.SESSION_RESUMED, {
            "server_sequence": session.sequence}, sequenced=False)

    await manager.broadcast(session, ServerEventType.PARTICIPANT_JOINED,
                            _participant_snapshot(str(rp.participant_id), rp),
                            to=[v for k, v in session.participants.items()
                                if k != str(rp.participant_id)])

    # ---- receive loop ---------------------------------------------------- #
    receive_task: asyncio.Task | None = None
    try:
        while True:
            try:
                message = await asyncio.wait_for(ws.receive(), timeout=RECEIVE_TIMEOUT_S)
            except asyncio.TimeoutError:
                await ws.send_text(json.dumps({
                    "version": 1, "type": ServerEventType.RECONNECT_REQUIRED,
                    "session_id": session.session_id,
                    "data": {"reason": "heartbeat_timeout"}}))
                break
            if message.get("type") == "websocket.disconnect":
                break

            # binary frame = audio chunk from this participant
            if (bdata := message.get("bytes")) is not None:
                await pl.get_pipeline(session).feed_audio(rp.participant_id, bdata)
                # relay original audio to original/mixed listeners (WS transport)
                await manager.relay_audio(session, rp.participant_id, bdata)
                continue

            tdata = message.get("text")
            if not tdata:
                continue
            try:
                event = parse_client_event(tdata)
            except Exception:
                await _send_error(ws, "invalid_event", "Could not parse event JSON.")
                continue

            try:
                await _handle_event(ws, session, rp, event)
            except WebSocketDisconnect:
                raise
            except Exception as e:
                log.exception("event handling failed: %s", event.type)
                await _send_error(ws, "internal_error", str(e)[:200],
                                  recoverable=True)
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("realtime ws crashed")
    finally:
        met.WS_CONNECTIONS.dec()
        manager.detach_ws(session, rp.participant_id)
        still_connected = any(p.connected for k, p in session.participants.items()
                              if k != str(rp.participant_id))
        if not still_connected:
            # keep session state for grace-period reconnects (PDD §38);
            # a sweeper closes long-dead sessions.
            rp.connected = False
        rp_in_session = session.participants.get(str(rp.participant_id))
        if rp_in_session is not None:
            rp_in_session.connected = False
            rp_in_session.ws = None
        with contextlib.suppress(Exception):
            await manager.broadcast(
                session, ServerEventType.PARTICIPANT_LEFT,
                {"participant_id": str(rp.participant_id)},
                to=[v for v in session.participants.values() if v.connected])
        log.info("ws closed for participant %s (session %s)", rp.participant_id,
                 session.session_id)


def _auth(ticket: str, meeting_id: str) -> tuple[str, uuid.UUID]:
    if not ticket:
        raise AuthenticationError("Missing realtime ticket.")
    try:
        sid, pid = verify_session_ticket(ticket)
        return sid, uuid.UUID(pid)
    except AuthenticationError:
        raise
    except Exception as e:
        raise AuthenticationError(f"Invalid ticket: {e}")


def _dev_flags() -> dict:
    from gt_ai.types import Task
    from app.ai import ai
    return {
        "stt_dev_mode": ai.is_dev_mode(Task.STT),
        "mt_dev_mode": ai.is_dev_mode(Task.MT),
        "tts_dev_mode": ai.is_dev_mode(Task.TTS),
    }


def _participant_snapshot(key: str, p: RtParticipant) -> dict:
    return {
        "participant_id": key, "display_name": p.display_name,
        "speak_lang": p.speak_lang, "hear_lang": p.hear_lang,
        "audio_mode": p.audio_mode, "connected": p.connected,
    }


async def _send_error(ws: WebSocket, code: str, message: str,
                      recoverable: bool = False) -> None:
    with contextlib.suppress(Exception):
        await ws.send_text(json.dumps({
            "version": 1, "type": ServerEventType.ERROR,
            "data": {"code": code, "message": message, "recoverable": recoverable},
            "timestamp": time.time()}))


async def _handle_event(ws: WebSocket, session, rp: RtParticipant, event) -> None:
    data = event.data or {}
    pipe = pl.get_pipeline(session)

    if event.type == ClientEventType.PING:
        await ws.send_text(json.dumps({
            "version": 1, "type": ServerEventType.PONG,
            "session_id": session.session_id,
            "data": {"client_ts": data.get("ts"), "server_ts": time.time() * 1000},
            "sequence": 0}))

    elif event.type == ClientEventType.SESSION_RESUME:
        last_seq = int(data.get("last_sequence", 0))
        missed = manager.replay_since(session, last_seq)
        await ws.send_text(json.dumps({
            "version": 1, "type": ServerEventType.SESSION_RESUMED,
            "session_id": session.session_id,
            "data": {"resumed_from": last_seq, "replayed": len(missed),
                     "server_sequence": session.sequence}}))
        for raw in missed:
            await ws.send_text(raw)
        met.RECONNECTS.inc()

    elif event.type == ClientEventType.AUDIO_START:
        sample_rate = int(data.get("sample_rate", 16000))
        if sample_rate != 16000:
            await _send_error(ws, "unsupported_sample_rate",
                              "Server expects 16kHz mono PCM16; resample client-side.",
                              recoverable=True)
            return
        pipe.start_speaker(rp)
        await manager.broadcast(session, ServerEventType.AUDIO_STARTED,
                                {"participant_id": str(rp.participant_id)})

    elif event.type == ClientEventType.AUDIO_CHUNK:
        b64 = data.get("audio_base64", "")
        if b64:
            try:
                pcm = base64.b64decode(b64)
            except Exception:
                await _send_error(ws, "invalid_audio", "audio_base64 not decodable.",
                                  recoverable=True)
                return
            await pipe.feed_audio(rp.participant_id, pcm)

    elif event.type == ClientEventType.AUDIO_STOP:
        pipe.stop_speaker(rp.participant_id)
        await manager.broadcast(session, ServerEventType.AUDIO_STOPPED,
                                {"participant_id": str(rp.participant_id)})

    elif event.type == ClientEventType.TRANSCRIPT_INJECT:
        try:
            await pipe.inject_transcript(rp, data.get("text", ""),
                                         data.get("language", ""))
        except Exception as e:
            await _send_error(ws, "inject_disabled", str(e)[:200])

    elif event.type == ClientEventType.PREFERENCES_UPDATE:
        speak = data.get("speak_lang")
        hear = data.get("hear_lang")
        audio_mode = data.get("audio_mode")
        captions = data.get("captions_enabled")
        async with db_session() as db:
            from app.services import meeting_service
            pref = await meeting_service.update_preference(
                db, rp.participant_id, speak_lang=speak, hear_lang=hear,
                audio_mode=audio_mode, captions_enabled=captions)
        if speak:
            rp.speak_lang = speak
        if hear:
            rp.hear_lang = hear
        if audio_mode:
            rp.audio_mode = audio_mode
        if captions is not None:
            rp.captions_enabled = bool(captions)
        await manager.broadcast(session, ServerEventType.LANGUAGE_CHANGED, {
            "participant_id": str(rp.participant_id),
            "display_name": rp.display_name,
            "speak_lang": rp.speak_lang, "hear_lang": rp.hear_lang,
            "audio_mode": rp.audio_mode})

    elif event.type == ClientEventType.CHAT_SEND:
        text = (data.get("text") or "").strip()
        if not text:
            return
        async with db_session() as db:
            meeting = await db.get(M.Meeting, session.meeting_id)
            participant = await db.get(M.Participant, rp.participant_id)
            if meeting is None or participant is None:
                await _send_error(ws, "not_found", "Meeting/participant gone.")
                return
            # dedup targets: distinct hear languages of connected participants
            targets = sorted({p.hear_lang for p in session.participants.values()
                              if p.connected and p.hear_lang})
            msg = await chat_service.send_message(
                db, meeting=meeting, sender=participant, text=text,
                target_langs=targets, org_id=session.org_id, user_id=rp.user_id)
        await manager.broadcast(session, ServerEventType.CHAT_MESSAGE, {
            "id": str(msg.id), "seq": msg.seq,
            "sender_name": msg.sender_name,
            "original_text": msg.original_text,
            "detected_lang": msg.detected_lang,
            "translations": msg.translations_json,
            "created_at": msg.created_at.isoformat(),
        }, speaker_id=str(rp.participant_id))

    elif event.type == ClientEventType.MEDIA_STATE:
        camera = bool(data.get("camera", False))
        screen = bool(data.get("screen", False))
        hand = bool(data.get("hand", False))
        mic = bool(data.get("mic", False))
        await manager.broadcast(session, ServerEventType.MEDIA_STATE, {
            "participant_id": str(rp.participant_id),
            "camera": camera,
            "screen": screen,
            "hand": hand,
            "mic": mic,
        }, speaker_id=str(rp.participant_id))

    elif event.type == ClientEventType.SIGNAL:
        target_id = str(data.get("target_id", "")).strip().lower()
        signal_data = data.get("signal")
        target_p = session.participants.get(target_id)
        if not target_p and target_id:
            # Flexible match in case of formatting or hyphen discrepancies
            clean_target = target_id.replace("-", "")
            for p in session.participants.values():
                if str(p.participant_id).lower() == target_id or str(p.participant_id).replace("-", "").lower() == clean_target:
                    target_p = p
                    break
        if target_p and target_p.ws:
            with contextlib.suppress(Exception):
                await target_p.ws.send_text(json.dumps({
                    "version": 1,
                    "type": ServerEventType.SIGNAL,
                    "session_id": session.session_id,
                    "data": {
                        "sender_id": str(rp.participant_id),
                        "signal": signal_data,
                    },
                    "timestamp": time.time(),
                }))
        elif not target_id:
            await manager.broadcast(session, ServerEventType.SIGNAL, {
                "sender_id": str(rp.participant_id),
                "signal": signal_data,
            }, speaker_id=str(rp.participant_id))

    else:
        await _send_error(ws, "unknown_event", f"Unknown event type: {event.type}",
                          recoverable=True)


# --------------------------------------------------------------------------- #
# Session sweeper: close sessions with no connected participants after grace
# --------------------------------------------------------------------------- #

GRACE_PERIOD_S = 300


async def session_sweeper() -> None:
    while True:
        await asyncio.sleep(60)
        try:
            now = time.time()
            for sid in list(manager._sessions.keys()):
                s = manager.get_session(sid)
                if s is None:
                    continue
                any_connected = any(p.connected for p in s.participants.values())
                if not any_connected and now - s.created_at > GRACE_PERIOD_S \
                        and now - max((p.joined_at for p in s.participants.values()),
                                      default=0) > GRACE_PERIOD_S:
                    await manager.close_session(sid)
        except Exception:
            log.exception("session sweeper error")
