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
from app.services import chat_service, meeting_service

log = logging.getLogger("app.realtime.ws")

router = APIRouter()

HEARTBEAT_INTERVAL_S = 25
RECEIVE_TIMEOUT_S = 90


@router.websocket("/ws/meetings/{meeting_id}")
@router.websocket("/ws/realtime")
async def realtime_ws(
    ws: WebSocket,
    meeting_id: str = "",
    ticket: str = Query(default=""),
    token: str = Query(default=""),
    join_token: str = Query(default=""),
):
    # ---- authenticate via ticket, JWT access token, or join_token ------- #
    user_id: uuid.UUID | None = None
    participant_id: uuid.UUID | None = None
    target_meeting_id: uuid.UUID | None = None

    if meeting_id:
        try:
            target_meeting_id = uuid.UUID(meeting_id)
        except Exception:
            await ws.close(code=4404, reason="invalid meeting id")
            return

    ticket_room: str | None = None
    if ticket:
        try:
            ticket_room, pid = verify_session_ticket(ticket, consume=True)
            participant_id = uuid.UUID(pid)
        except AuthenticationError as e:
            await ws.close(code=4401, reason=e.message)
            return
        except Exception as e:
            await ws.close(code=4401, reason=f"Invalid ticket: {e}")
            return
    elif token:
        try:
            from app.security import decode_token
            claims = decode_token(token, "access")
            user_id = uuid.UUID(claims["sub"])
        except Exception as e:
            await ws.close(code=4401, reason=f"Invalid token: {e}")
            return
    elif join_token:
        # Proceed to validate existing participant with matching guest_key
        pass
    else:
        await ws.close(code=4401, reason="Authentication required (valid ticket, token, or join_token required)")
        return

    async with db_session() as db:
        participant: M.Participant | None = None
        if participant_id is not None:
            participant = await db.get(M.Participant, participant_id)
        elif user_id is not None and target_meeting_id is not None:
            res = await db.execute(
                select(M.Participant).where(
                    M.Participant.meeting_id == target_meeting_id,
                    M.Participant.user_id == user_id,
                )
            )
            participant = res.scalars().first()
            if participant is None:
                meeting = await db.get(M.Meeting, target_meeting_id)
                if meeting is None:
                    await ws.close(code=4404, reason="meeting not found")
                    return
                # Verify user belongs to the meeting's organization or is platform admin
                mem_res = await db.execute(
                    select(M.OrganizationMember).where(
                        M.OrganizationMember.org_id == meeting.org_id,
                        M.OrganizationMember.user_id == user_id,
                        M.OrganizationMember.status == "active",
                    )
                )
                user = await db.get(M.User, user_id)
                if not mem_res.scalars().first() and not (user and user.is_platform_admin):
                    await ws.close(code=4403, reason="Forbidden: not a member of the meeting organization")
                    return
                dname = (user.name if user and user.name else (user.email.split("@")[0] if user else "Participant"))
                from app.services import meeting_service
                participant, _, _ = await meeting_service.join_meeting(
                    db, meeting, user_id=user_id, display_name=dname,
                    speak_lang="auto", hear_lang="en", audio_mode="translated"
                )
        elif join_token and target_meeting_id is not None:
            res = await db.execute(
                select(M.Participant).where(
                    M.Participant.meeting_id == target_meeting_id,
                    M.Participant.guest_key == join_token,
                )
            )
            participant = res.scalars().first()
            if participant is None:
                await ws.close(code=4401, reason="Invalid guest join token. Please join meeting via REST join endpoint first.")
                return

        if participant is None:
            await ws.close(code=4404, reason="participant not found")
            return

        if target_meeting_id is not None and participant.meeting_id != target_meeting_id:
            await ws.close(code=4403, reason="Forbidden: credential not valid for this meeting")
            return

        meeting = await db.get(M.Meeting, participant.meeting_id)
        if meeting is None or meeting.status not in ("scheduled", "live"):
            await ws.close(code=4410, reason="meeting not joinable")
            return

        if ticket and ticket_room and ticket_room not in (meeting.room_name, str(meeting.id)):
            await ws.close(code=4403, reason="Ticket room mismatch")
            return
        if meeting is None or meeting.status not in ("scheduled", "live"):
            await ws.close(code=4410, reason="meeting not joinable")
            return

        pref = (await db.execute(select(M.ParticipantPreference).where(
            M.ParticipantPreference.participant_id == participant.id))).scalars().first()
        meeting_id_uuid = meeting.id
        org_id = meeting.org_id
        room_name = meeting.room_name
        mode = meeting.mode
        db_seq = (await db.execute(
            select(func.coalesce(func.max(M.TranscriptSegment.seq), 0))
            .where(M.TranscriptSegment.meeting_id == meeting.id))).scalar() or 0
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

    from app import context
    ws_headers = dict(ws.headers) if hasattr(ws, "headers") else {}
    tp = ws_headers.get("traceparent")
    ws_trace_id = None
    if tp:
        parts = tp.split("-")
        if len(parts) >= 2 and len(parts[1]) == 32:
            ws_trace_id = parts[1]
    if not ws_trace_id:
        ws_trace_id = ws_headers.get("x-trace-id") or ws.query_params.get("trace_id") or uuid.uuid4().hex

    ws_req_id = ws_headers.get("x-request-id") or ws.query_params.get("request_id") or uuid.uuid4().hex[:16]
    context.new_ctx(
        request_id=ws_req_id,
        trace_id=ws_trace_id,
        tenant_id=str(org_id) if org_id else None,
        user_id=str(p_data["user_id"]) if p_data.get("user_id") else None,
        meeting_id=str(meeting_id_uuid),
    )

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
    old_ws: WebSocket | None = None
    old_task: asyncio.Task | None = None
    if existing is not None:
        rp.last_seq_seen = existing.last_seq_seen  # preserve resume position
        if existing.connected and existing.ws is not None and existing.ws != ws:
            old_ws = existing.ws
            old_task = existing.ws_task
    manager.add_participant(session, rp)
    manager.attach_ws(session, rp.participant_id, ws)
    rp.ws_task = asyncio.current_task()
    if old_ws is not None:
        with contextlib.suppress(Exception):
            await old_ws.close(code=4409, reason="duplicate_connection_superseded")
    if old_task is not None and not old_task.done():
        old_task.cancel()
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

            # Desi Voice Streaming standard: {"source_media_chunk": {"data": "<base64_audio>"}}
            if "source_media_chunk" in tdata:
                try:
                    payload = json.loads(tdata)
                    if "source_media_chunk" in payload and "data" in payload["source_media_chunk"]:
                        chunk_b64 = payload["source_media_chunk"]["data"]
                        raw_bytes = base64.b64decode(chunk_b64)
                        await pl.get_pipeline(session).feed_audio(rp.participant_id, raw_bytes)
                        await manager.relay_audio(session, rp.participant_id, raw_bytes)
                        continue
                except Exception as ex:
                    log.warning("Failed decoding source_media_chunk: %s", ex)
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
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:
        log.exception("realtime ws crashed")
    finally:
        met.WS_CONNECTIONS.dec()
        manager.detach_ws(session, rp.participant_id, ws=ws)
        rp_in_session = session.participants.get(str(rp.participant_id))
        if rp_in_session is None or not rp_in_session.connected or rp_in_session.ws == ws:
            if rp_in_session is not None and rp_in_session.ws == ws:
                rp_in_session.connected = False
                rp_in_session.ws = None
            with contextlib.suppress(Exception):
                await manager.broadcast(
                    session, ServerEventType.PARTICIPANT_LEFT,
                    {"participant_id": str(rp.participant_id)},
                    to=[v for v in session.participants.values() if v.connected])
            # Mark participant status as left in database so GET /participants stays clean
            with contextlib.suppress(Exception):
                async with db_session() as db:
                    await meeting_service.leave_participant(db, rp.participant_id)
        log.info("ws closed for participant %s (session %s)", rp.participant_id,
                 session.session_id)


def _auth(ticket: str, meeting_id: str) -> tuple[str, uuid.UUID]:
    if not ticket:
        raise AuthenticationError("Missing realtime ticket.")
    try:
        sid, pid = verify_session_ticket(ticket, consume=True)
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

    elif event.type == ClientEventType.SESSION_JOIN:
        if "speaking_language" in data:
            rp.speak_lang = data["speaking_language"]
        elif "speak_lang" in data:
            rp.speak_lang = data["speak_lang"]
        if "listening_language" in data:
            rp.hear_lang = data["listening_language"]
        elif "hear_lang" in data:
            rp.hear_lang = data["hear_lang"]
        if "audio_mode" in data:
            rp.audio_mode = data["audio_mode"]
        if "display_name" in data and data["display_name"]:
            rp.display_name = data["display_name"]

        last_seq = int(data.get("last_sequence", 0))
        if last_seq > 0:
            missed = manager.replay_since(session, last_seq)
            await ws.send_text(json.dumps({
                "version": 1, "type": ServerEventType.SESSION_RESUMED,
                "session_id": session.session_id,
                "data": {"resumed_from": last_seq, "replayed": len(missed),
                         "server_sequence": session.sequence}}))
            for raw in missed:
                await ws.send_text(raw)
            met.RECONNECTS.inc()

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
        speak = data.get("speak_lang") or data.get("speaking_language")
        hear = data.get("hear_lang") or data.get("listening_language")
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
