"""Realtime WebSocket endpoint: /ws/meetings/{meeting_id}.

Auth: JWT bearer (member of the org) OR the meeting join_token (guest participants).
Transport: JSON control events + binary PCM16 mono 16kHz frames from the microphone.
Reconnect: client re-joins with last_sequence → server replays buffered events
(session.resumed), reconciles preferences from DB. No transcript loss: finals are persisted
before broadcast; the ring buffer only accelerates resume.
"""
from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from globaltalk.core.config import settings
from globaltalk.core.db import SessionLocal
from globaltalk.core.logging import get_logger
from globaltalk.core.security import decode_token, sha256
from globaltalk.models import (ChatMessage, Meeting, OrganizationMember, Participant,
                               ParticipantPreference, TranslationSegment, User)
from globaltalk.realtime.audio_pipeline import AudioPipeline
from globaltalk.realtime.hub import ParticipantConn, hub, spawn
from globaltalk.realtime.protocol import EventType, client_event_type
from globaltalk.services.chat import translate_chat_for_listeners
from globaltalk.services.meetings import next_chat_sequence, next_segment_sequence

log = get_logger("ws")
router = APIRouter()


def _authenticate(db: Session, meeting: Meeting, token: str | None,
                  join_token: str | None) -> tuple[User | None, bool]:
    """Returns (user_or_None, allowed). Guests allowed only with a valid join_token."""
    if token:
        try:
            payload = decode_token(token, "access")
            user = db.get(User, payload["sub"])
            if user and user.is_active:
                member = (db.query(OrganizationMember)
                          .filter(OrganizationMember.org_id == meeting.org_id,
                                  OrganizationMember.user_id == user.id).first())
                if member or user.is_platform_admin:
                    return user, True
        except Exception:
            pass
    if join_token and meeting.join_token:
        from globaltalk.core.security import constant_time_eq
        if constant_time_eq(join_token, meeting.join_token):
            return None, True
    return None, False


@router.websocket("/ws/meetings/{meeting_id}")
async def meeting_ws(ws: WebSocket, meeting_id: str,
                     token: str | None = Query(default=None),
                     join_token: str | None = Query(default=None)):
    db = SessionLocal()
    meeting = db.get(Meeting, meeting_id)
    if not meeting:
        await ws.close(code=4404, reason="meeting_not_found")
        db.close()
        return
    user, allowed = _authenticate(db, meeting, token, join_token)
    if not allowed:
        await ws.close(code=4401, reason="unauthorized")
        db.close()
        return
    await ws.accept()
    conn: ParticipantConn | None = None
    session = None
    pipeline: AudioPipeline | None = None
    try:
        session = hub.get_or_create(meeting.id, meeting.room_name, meeting.org_id)
        conn, pipeline = await _handshake(ws, db, meeting, session, user)
        if conn is None:
            return
        await _event_loop(ws, db, session, conn, pipeline)
    except WebSocketDisconnect:
        log.info("ws_disconnected", extra={"meeting_id": meeting_id})
    except Exception:
        log.exception("ws_error", extra={"meeting_id": meeting_id})
        with contextlib.suppress(Exception):
            await ws.close(code=1011)
    finally:
        if conn and session:
            await _leave(db, session, conn, pipeline)
        db.close()
        hub.drop_if_empty(meeting_id)


async def _handshake(ws: WebSocket, db: Session, meeting: Meeting, session,
                     user: User | None) -> tuple[ParticipantConn | None, AudioPipeline | None]:
    """Wait for session.join (with optional last_sequence for resume)."""
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=15)
    except asyncio.TimeoutError:
        await ws.close(code=4408, reason="join_timeout")
        return None, None
    data = json.loads(raw)
    if client_event_type(data) != "session.join":
        await ws.send_json({"version": 1, "type": EventType.ERROR,
                            "error": {"code": "expected_session_join"}})
        await ws.close(code=4400)
        return None, None

    participant_id = data.get("participant_id")
    display_name = (data.get("display_name") or
                    (user.full_name if user else "Guest")).strip()[:120] or "Guest"
    speaking = str(data.get("speaking_language", "AUTO"))[:16]
    listening = str(data.get("listening_language", "en"))[:16]
    audio_mode = data.get("audio_mode", "translated")
    caption_mode = data.get("caption_mode", "both")
    latency_mode = data.get("latency_mode", settings.realtime_latency_mode)
    last_sequence = int(data.get("last_sequence") or 0)
    wants_resume = bool(data.get("resume")) or last_sequence > 0

    participant = None
    if participant_id:
        participant = (db.query(Participant)
                       .filter(Participant.id == participant_id,
                               Participant.meeting_id == meeting.id).first())
    if participant is None:
        participant = Participant(meeting_id=meeting.id,
                                  user_id=user.id if user else None,
                                  display_name=display_name,
                                  identity=f"{display_name}-{meeting.room_name}"[:160],
                                  status="joined")
        db.add(participant)
        db.flush()
        db.add(ParticipantPreference(participant_id=participant.id,
                                     speaking_language=speaking,
                                     listening_language=listening,
                                     audio_mode=audio_mode, caption_mode=caption_mode,
                                     latency_mode=latency_mode))
        db.commit()
    else:
        participant.status = "joined"
        participant.display_name = display_name or participant.display_name
        pref = participant.preferences
        if pref is None:
            pref = ParticipantPreference(participant_id=participant.id)
            db.add(pref)
        pref.speaking_language = speaking
        pref.listening_language = listening
        pref.audio_mode = audio_mode
        pref.caption_mode = caption_mode
        pref.latency_mode = latency_mode
        db.commit()

    conn = ParticipantConn(participant_id=participant.id, identity=participant.identity,
                           display_name=participant.display_name, ws=ws,
                           speaking_language=speaking, listening_language=listening,
                           audio_mode=audio_mode, caption_mode=caption_mode,
                           latency_mode=latency_mode)
    session.participants[participant.id] = conn
    pipeline = AudioPipeline(session, conn)
    session.pipelines[participant.id] = pipeline

    resumed = wants_resume and session._sequence > 0
    if resumed:
        evt = session.record(EventType.SESSION_RESUMED, participant_id=participant.id,
                             resumed_from_sequence=last_sequence)
        await session.send(conn, evt)
        for past in session.events_after(last_sequence):
            await session.send(conn, past)
    else:
        evt = session.record(EventType.SESSION_CREATED if len(session.participants) == 1
                             else EventType.SESSION_UPDATED,
                             participant_id=participant.id,
                             meeting_id=meeting.id, room_name=meeting.room_name,
                             transport="livekit" if settings.livekit_configured else "websocket")
        await session.send(conn, evt)

    joined = session.record(EventType.PARTICIPANT_JOINED, speaker_id=participant.id,
                            participant_id=participant.id, display_name=participant.display_name,
                            speaking_language=speaking, listening_language=listening,
                            audio_mode=audio_mode, caption_mode=caption_mode,
                            participants=[_participant_snapshot(p)
                                          for p in session.participants.values()])
    await session.broadcast(joined)
    if meeting.status != "live":
        meeting.status = "live"
        from datetime import datetime, timezone
        meeting.started_at = meeting.started_at or datetime.now(timezone.utc)
        db.commit()
    return conn, pipeline


def _participant_snapshot(p: ParticipantConn) -> dict:
    return {"participant_id": p.participant_id, "display_name": p.display_name,
            "speaking_language": p.speaking_language, "listening_language": p.listening_language,
            "audio_mode": p.audio_mode, "connected": p.connected}


async def _event_loop(ws: WebSocket, db: Session, session, conn: ParticipantConn,
                      pipeline: AudioPipeline) -> None:
    while True:
        msg = await ws.receive()
        if msg.get("type") == "websocket.disconnect":
            break
        if (b := msg.get("bytes")) is not None:
            if not conn.audio_active:
                conn.audio_active = True
                evt = session.record(EventType.AUDIO_STARTED, speaker_id=conn.participant_id,
                                     sample_rate=settings.audio_sample_rate,
                                     transport="websocket_pcm16")
                await session.broadcast(evt)
            await pipeline.feed(b)
            continue
        text = msg.get("text")
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        etype = client_event_type(data)

        if etype == "ping":
            await ws.send_json({"version": 1, "type": EventType.PONG,
                                "client_ts": data.get("ts")})

        elif etype == "preferences.update":
            changed = {}
            pref = (db.query(ParticipantPreference)
                    .filter(ParticipantPreference.participant_id == conn.participant_id).first())
            for field_conn, field_db in (("speaking_language", "speaking_language"),
                                         ("listening_language", "listening_language"),
                                         ("audio_mode", "audio_mode"),
                                         ("caption_mode", "caption_mode"),
                                         ("latency_mode", "latency_mode")):
                if field_conn in data:
                    val = str(data[field_conn])[:24]
                    setattr(conn, field_conn, val)
                    if pref:
                        setattr(pref, field_db, val)
                    changed[field_conn] = val
            db.commit()
            evt = session.record(EventType.LANGUAGE_CHANGED, speaker_id=conn.participant_id,
                                 participant_id=conn.participant_id, **changed)
            await session.broadcast(evt)

        elif etype == "chat.send":
            await _handle_chat(ws, db, session, conn, data)

        elif etype == "audio.stopped":
            conn.audio_active = False
            evt = session.record(EventType.AUDIO_STOPPED, speaker_id=conn.participant_id)
            await session.broadcast(evt)

        else:
            await ws.send_json({"version": 1, "type": EventType.ERROR,
                                "error": {"code": "unknown_event", "received": etype}})


async def _handle_chat(ws: WebSocket, db: Session, session, conn: ParticipantConn,
                       data: dict) -> None:
    original = str(data.get("text", ""))[:4000].strip()
    if not original:
        return
    seq = next_chat_sequence(db, session.meeting_id)
    from globaltalk.services.translation import detect_text_language
    detected, _conf = detect_text_language(db, original)
    row = ChatMessage(org_id=session.org_id, meeting_id=session.meeting_id,
                      participant_id=conn.participant_id, sequence=seq,
                      original_text=original, detected_language=detected)
    db.add(row)
    db.commit()
    evt = session.record(EventType.CHAT_MESSAGE, speaker_id=conn.participant_id,
                         message_id=row.id, participant_id=conn.participant_id,
                         display_name=conn.display_name, chat_sequence=seq,
                         original_text=original, language=detected)
    await session.broadcast(evt)
    # Translate original → each distinct listening language present (dedup), never mutate it.
    spawn(translate_chat_for_listeners(session, db, row.id, original, detected),
          name=f"chat-translate-{row.id[:8]}")


async def _leave(db: Session, session, conn: ParticipantConn,
                 pipeline: AudioPipeline | None) -> None:
    conn.connected = False
    if pipeline:
        pipeline.shutdown()
    session.pipelines.pop(conn.participant_id, None)
    participant = (db.query(Participant)
                   .filter(Participant.id == conn.participant_id).first())
    if participant:
        from datetime import datetime, timezone
        participant.status = "left"
        participant.left_at = datetime.now(timezone.utc)
        db.commit()
    try:
        evt = session.record(EventType.PARTICIPANT_LEFT, speaker_id=conn.participant_id,
                             participant_id=conn.participant_id,
                             display_name=conn.display_name)
        await session.broadcast(evt, exclude=conn.participant_id)
    except Exception:
        pass
    session.participants.pop(conn.participant_id, None)
