"""Meetings router: create/join/participants/preferences/transcript/tokens
(PDD §12, §20, §33). Also standalone voice sessions (PDD §19 API product).
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import models as M
from app.db.base import utcnow
from app.db.session import get_db
from app.deps import Principal, get_principal_optional, require_org_user, require_scope
from app.errors import NotFoundError, ValidationError
from app.realtime import livekit_bridge
from app.schemas import (
    JoinMeetingRequest, JoinMeetingResponse, MeetingCreate, MeetingDetailOut,
    MeetingOut, ParticipantFullOut, ParticipantOut, PreferenceOut,
    PreferenceUpdate, PreferenceUpdate as _PrefUpd, TranscriptSegmentOut,
    VoiceSessionCreate,
)
from app.security import create_session_ticket
from app.services import audit_service, meeting_service, webhook_service

log = logging.getLogger("app.routers.meetings")

router = APIRouter(prefix="/api/v1", tags=["meetings"])


async def _meeting_or_404(db: AsyncSession, meeting_id: uuid.UUID,
                          principal: Principal) -> M.Meeting:
    return await meeting_service.get_meeting_for_org(db, meeting_id, principal.org_id)


@router.post("/meetings", response_model=MeetingDetailOut, status_code=201)
async def create_meeting(body: MeetingCreate,
                         principal: Principal = Depends(require_org_user),
                         db: AsyncSession = Depends(get_db)):
    principal.require("create_meeting")
    from app.deps import flag_enabled
    if body.mode == "livekit" and not settings.livekit_enabled:
        raise ValidationError("LiveKit transport is not configured on this server; "
                              "use mode='ws' for realtime translation sessions.")
    if not await flag_enabled(db, "voice_translation", principal.org_id):
        from app.errors import FeatureDisabledError
        raise FeatureDisabledError("Voice translation is disabled for this organization.")
    # validate languages against capability registry
    from app.services.translation_service import validate_pair
    await validate_pair(db, "en", body.hear_lang, need_realtime=True)
    if body.speak_lang != "auto":
        await validate_pair(db, body.speak_lang, body.hear_lang, need_realtime=True)

    meeting, participant = await meeting_service.create_meeting(
        db, org_id=principal.org_id, created_by=principal.user_id,
        title=body.title, mode=body.mode, speak_lang=body.speak_lang,
        hear_lang=body.hear_lang)
    if principal.user:
        participant.display_name = principal.user.name or principal.user.email.split("@")[0]
        await db.commit()
    if meeting.mode == "livekit":
        await livekit_bridge.ensure_room(meeting.room_name)
    return await _detail(db, meeting, principal)


@router.get("/meetings", response_model=list[MeetingOut])
async def list_meetings(principal: Principal = Depends(require_org_user),
                        db: AsyncSession = Depends(get_db),
                        limit: int = Query(default=50, le=200),
                        status: str = Query(default="")):
    q = select(M.Meeting).where(M.Meeting.org_id == principal.org_id)
    if status:
        q = q.where(M.Meeting.status == status)
    res = await db.execute(q.order_by(M.Meeting.created_at.desc()).limit(limit))
    return [MeetingOut.model_validate(m) for m in res.scalars().all()]


async def _detail(db: AsyncSession, meeting: M.Meeting,
                  principal: Principal | None = None) -> MeetingDetailOut:
    participants = await meeting_service.list_participants(db, meeting.id)
    base = MeetingDetailOut.model_validate(meeting)
    base.participants = [
        ParticipantFullOut(
            participant=ParticipantOut.model_validate(p),
            preference=PreferenceOut.model_validate(pref) if pref else None)
        for p, pref in participants]
    if meeting.mode == "livekit" and livekit_bridge.enabled() and principal and principal.user_id:
        my_p = next((p for p, _ in participants if p.user_id == principal.user_id), None)
        if my_p:
            base.livekit = livekit_bridge.join_token(
                meeting.room_name, my_p.livekit_identity or str(my_p.id),
                my_p.display_name or (principal.user.name if principal.user else "Participant"),
                {"participant_id": str(my_p.id), "org_id": str(meeting.org_id), "meeting_id": str(meeting.id)})
    return base


@router.get("/meetings/{meeting_id}", response_model=MeetingDetailOut)
async def get_meeting(meeting_id: uuid.UUID,
                      principal: Principal | None = Depends(get_principal_optional),
                      db: AsyncSession = Depends(get_db)):
    meeting = await db.get(M.Meeting, meeting_id)
    if meeting is None:
        raise NotFoundError("Meeting not found.")
    
    # Cross-tenant isolation check: if principal is authenticated, enforce tenant ownership or participation
    participants = await meeting_service.list_participants(db, meeting.id)
    is_org_member = bool(principal and principal.org_id and principal.org_id == meeting.org_id)
    is_participant = bool(principal and principal.user_id and any(p.user_id == principal.user_id for p, _ in participants))

    if principal and principal.org_id and not (is_org_member or is_participant):
        # A member of another org cannot view this meeting unless explicitly added
        raise NotFoundError("Meeting not found.")

    if meeting.status == "ended" and not is_org_member:
        raise NotFoundError("Meeting not found.")

    return await _detail(db, meeting, principal)


@router.post("/meetings/{meeting_id}/join", response_model=JoinMeetingResponse)
async def join_meeting(meeting_id: uuid.UUID, body: JoinMeetingRequest,
                       principal: Principal | None = Depends(get_principal_optional),
                       db: AsyncSession = Depends(get_db)):
    meeting = await db.get(M.Meeting, meeting_id)
    if meeting is None:
        raise NotFoundError("Meeting not found.")
    if meeting.status not in ("scheduled", "live"):
        raise ValidationError("Meeting is not joinable.",
                              details={"status": meeting.status})
    from app.services.translation_service import validate_pair
    await validate_pair(db, "en", body.hear_lang, need_realtime=True)

    user_id = principal.user_id if principal else None
    display = body.display_name
    if not display and principal and principal.user:
        display = principal.user.name or principal.user.email.split("@")[0]
    display = display or "Guest Participant"

    p, pref, session_key = await meeting_service.join_meeting(
        db, meeting, user_id=user_id, display_name=display,
        speak_lang=body.speak_lang, hear_lang=body.hear_lang,
        audio_mode=body.audio_mode, guest_key=body.guest_key or "")

    if meeting.status == "live" and meeting.started_at:
        pass  # webhook fired on transition below
    ticket = create_session_ticket(meeting.room_name, str(p.id))
    rt_url = f"{settings.web_origin.replace('http', 'ws', 1) if settings.web_origin.startswith('http') else 'ws://localhost:8000'}"
    resp = JoinMeetingResponse(
        meeting_id=meeting.id, participant_id=p.id, session_key=session_key,
        rt_url=f"/ws/realtime?ticket={ticket}",
        livekit=None)
    if meeting.mode == "livekit":
        resp.livekit = livekit_bridge.join_token(
            meeting.room_name, p.livekit_identity or str(p.id),
            p.display_name,
            {"participant_id": str(p.id), "speak_lang": pref.speak_lang,
             "hear_lang": pref.hear_lang, "audio_mode": pref.audio_mode})
    try:
        await webhook_service.dispatch(db, meeting.org_id, "meeting.started",
                                       {"meeting_id": str(meeting.id),
                                        "title": meeting.title})
    except Exception:
        log.debug("webhook dispatch skipped")
    return resp


@router.get("/meetings/{meeting_id}/participants", response_model=list[dict])
async def get_participants(request: Request,
                           meeting_id: uuid.UUID,
                           principal: Principal | None = Depends(get_principal_optional),
                           db: AsyncSession = Depends(get_db)):
    """List participants for a meeting with their preferences."""
    meeting = await db.get(M.Meeting, meeting_id)
    if meeting is None:
        raise NotFoundError("Meeting not found.")
    participants = await meeting_service.list_participants(db, meeting.id)

    # BOLA protection: verify caller has legitimate membership or participation in this meeting
    is_org_member = bool(principal and principal.org_id and principal.org_id == meeting.org_id)
    is_participant = bool(principal and principal.user_id and any(p.user_id == principal.user_id for p, _ in participants))

    p_header = request.headers.get("x-participant-id") or request.query_params.get("participant_id")
    is_guest = False
    if p_header:
        try:
            p_uuid = uuid.UUID(p_header)
            is_guest = any(p.id == p_uuid for p, _ in participants)
        except ValueError:
            pass

    if not (is_org_member or is_participant or is_guest):
        raise NotFoundError("Meeting not found.")

    out = []
    for p, pref in participants:
        out.append({
            "id": str(p.id),
            "display_name": p.display_name or "Participant",
            "status": p.status or "joined",
            "speaking_language": pref.speak_lang if pref else "auto",
            "listening_language": pref.hear_lang if pref else "en",
            "audio_mode": pref.audio_mode if pref else "translated",
            "caption_mode": getattr(pref, "caption_mode", "both") or "both",
        })
    return out


@router.post("/meetings/{meeting_id}/tokens", response_model=dict)
async def meeting_token(meeting_id: uuid.UUID,
                        principal: Principal = Depends(require_org_user),
                        db: AsyncSession = Depends(get_db)):
    """Short-lived realtime ticket + (optional) LiveKit join token."""
    meeting = await _meeting_or_404(db, meeting_id, principal)
    participants = await meeting_service.list_participants(db, meeting.id)
    mine = next((p for p, _ in participants
                 if principal.user_id and p.user_id == principal.user_id), None)
    if mine is None:
        raise NotFoundError("Join the meeting first.")
    ticket = create_session_ticket(meeting.room_name, str(mine.id))
    out = {"ticket": ticket, "ws_url": f"/ws/realtime?ticket={ticket}",
           "participant_id": str(mine.id)}
    if meeting.mode == "livekit":
        out["livekit"] = livekit_bridge.join_token(
            meeting.room_name, mine.livekit_identity or str(mine.id),
            mine.display_name, {"participant_id": str(mine.id)})
    return out


@router.put("/meetings/{meeting_id}/participants/{participant_id}/preferences",
            response_model=PreferenceOut)
async def update_preferences(meeting_id: uuid.UUID, participant_id: uuid.UUID,
                             body: PreferenceUpdate,
                             principal: Principal = Depends(require_org_user),
                             db: AsyncSession = Depends(get_db)):
    meeting = await _meeting_or_404(db, meeting_id, principal)
    participants = await meeting_service.list_participants(db, meeting.id)
    target = next((p for p, _ in participants if p.id == participant_id), None)
    if target is None:
        raise NotFoundError("Participant not found.")
    # authorization: self, host, or manager+
    is_self = principal.user_id and target.user_id == principal.user_id
    if not is_self:
        principal.require("manage_members")
    if body.hear_lang:
        from app.services.translation_service import validate_pair
        await validate_pair(db, "en", body.hear_lang, need_realtime=True)
    pref = await meeting_service.update_preference(
        db, participant_id, speak_lang=body.speak_lang, hear_lang=body.hear_lang,
        audio_mode=body.audio_mode, captions_enabled=body.captions_enabled)
    # hot-update live routing table if session active
    from app.realtime.session_manager import manager
    session = manager.get_session_for_meeting(meeting.id)
    if session:
        rp = session.participants.get(str(participant_id))
        if rp:
            if body.speak_lang:
                rp.speak_lang = body.speak_lang
            if body.hear_lang:
                rp.hear_lang = body.hear_lang
            if body.audio_mode:
                rp.audio_mode = body.audio_mode
            if body.captions_enabled is not None:
                rp.captions_enabled = body.captions_enabled
            await manager.broadcast(session, "language.changed", {
                "participant_id": str(participant_id),
                "display_name": rp.display_name,
                "speak_lang": rp.speak_lang, "hear_lang": rp.hear_lang,
                "audio_mode": rp.audio_mode})
    return PreferenceOut.model_validate(pref)


@router.get("/meetings/{meeting_id}/transcript",
            response_model=list[TranscriptSegmentOut])
async def get_transcript(meeting_id: uuid.UUID,
                         principal: Principal = Depends(require_org_user),
                         db: AsyncSession = Depends(get_db),
                         speaker_id: str = Query(default=""),
                         source_lang: str = Query(default=""),
                         target_lang: str = Query(default=""),
                         q: str = Query(default=""),
                         limit: int = Query(default=500, le=2000),
                         after_seq: int = Query(default=0)):
    """Multilingual transcript: source + all stored translations per segment.
    Supports speaker/language filtering + search (PDD §20)."""
    meeting = await _meeting_or_404(db, meeting_id, principal)
    principal.require("view_transcript")
    query = select(M.TranscriptSegment).where(
        M.TranscriptSegment.meeting_id == meeting.id,
        M.TranscriptSegment.is_final.is_(True),
        M.TranscriptSegment.seq > after_seq)
    if speaker_id:
        query = query.where(M.TranscriptSegment.speaker_id == uuid.UUID(speaker_id))
    if source_lang:
        query = query.where(M.TranscriptSegment.source_lang == source_lang)
    if q:
        query = query.where(M.TranscriptSegment.source_text.ilike(f"%{q}%"))
    res = await db.execute(query.order_by(M.TranscriptSegment.seq).limit(limit))
    segments = res.scalars().all()
    out = []
    for s in segments:
        item = TranscriptSegmentOut.model_validate(s)
        if target_lang:
            item.translations = [t for t in item.translations
                                 if t.target_lang == target_lang]
        out.append(item)
    return out


@router.get("/meetings/{meeting_id}/transcript/export")
async def export_transcript(meeting_id: uuid.UUID,
                            fmt: str = Query(default="json", pattern="^(json|txt|srt)$"),
                            principal: Principal = Depends(require_org_user),
                            db: AsyncSession = Depends(get_db)):
    from fastapi.responses import PlainTextResponse
    meeting = await _meeting_or_404(db, meeting_id, principal)
    principal.require("export_document")
    segments = await _all_segments(db, meeting.id)
    await audit_service.record(db, action="transcript.exported",
                               org_id=principal.org_id, actor_id=principal.user_id,
                               resource_type="meeting", resource_id=str(meeting.id),
                               details={"format": fmt})
    await db.commit()
    if fmt == "json":
        import json
        data = [{
            "seq": s.seq, "speaker": s.speaker_name, "lang": s.source_lang,
            "text": s.source_text, "start_ms": s.start_ms, "end_ms": s.end_ms,
            "translations": [{"lang": t.target_lang, "text": t.target_text,
                              "model": t.model} for t in s.translations],
        } for s in segments]
        return PlainTextResponse(json.dumps(data, ensure_ascii=False, indent=2),
                                 media_type="application/json",
                                 headers={"Content-Disposition":
                                          f'attachment; filename="transcript_{meeting_id}.json"'})
    if fmt == "srt":
        lines = []
        for i, s in enumerate(segments, 1):
            start = _srt_ts(s.start_ms or 0)
            end = _srt_ts(s.end_ms or (s.start_ms or 0) + 3000)
            lines.append(f"{i}\n{start} --> {end}\n{s.speaker_name}: {s.source_text}\n")
        return PlainTextResponse("\n".join(lines), media_type="text/plain",
                                 headers={"Content-Disposition":
                                          f'attachment; filename="transcript_{meeting_id}.srt"'})
    lines = [f"[{s.source_lang}] {s.speaker_name}: {s.source_text}" for s in segments]
    return PlainTextResponse("\n".join(lines), media_type="text/plain",
                             headers={"Content-Disposition":
                                      f'attachment; filename="transcript_{meeting_id}.txt"'})


def _srt_ts(ms: int) -> str:
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02},{milli:03}"


async def _all_segments(db: AsyncSession, meeting_id: uuid.UUID):
    res = await db.execute(select(M.TranscriptSegment).where(
        M.TranscriptSegment.meeting_id == meeting_id,
        M.TranscriptSegment.is_final.is_(True))
        .order_by(M.TranscriptSegment.seq))
    return res.scalars().all()


@router.post("/meetings/{meeting_id}/end", response_model=MeetingOut)
async def end_meeting(meeting_id: uuid.UUID,
                      principal: Principal = Depends(require_org_user),
                      db: AsyncSession = Depends(get_db)):
    meeting = await _meeting_or_404(db, meeting_id, principal)
    await meeting_service.end_meeting(db, meeting)
    from app.realtime.session_manager import manager
    session = manager.get_session_for_meeting(meeting.id)
    if session:
        await manager.broadcast(session, "session.updated",
                                {"status": "ended", "reason": "host_ended"})
        await manager.close_session(session.session_id)
    await webhook_service.dispatch(db, meeting.org_id, "meeting.ended",
                                   {"meeting_id": str(meeting.id)})
    await db.commit()
    return MeetingOut.model_validate(meeting)


@router.delete("/meetings/{meeting_id}", status_code=204)
async def delete_meeting(meeting_id: uuid.UUID,
                         principal: Principal = Depends(require_org_user),
                         db: AsyncSession = Depends(get_db)):
    meeting = await _meeting_or_404(db, meeting_id, principal)
    principal.require("delete_meeting")
    await db.delete(meeting)
    await audit_service.record(db, action="meeting.deleted",
                               org_id=principal.org_id, actor_id=principal.user_id,
                               resource_type="meeting", resource_id=str(meeting_id))
    await db.commit()


# --------------------------------------------------------------------------- #
# Standalone voice sessions (developer API product, PDD §19)
# --------------------------------------------------------------------------- #

voice_router = APIRouter(prefix="/api/v1/voice", tags=["voice"])


@voice_router.post("/session", response_model=dict, status_code=201)
async def create_voice_session(body: VoiceSessionCreate,
                               principal: Principal = Depends(require_org_user),
                               _scope=Depends(require_scope("voice")),
                               db: AsyncSession = Depends(get_db)):
    """Create a realtime speech-to-speech session and return its WS ticket.

    A voice session is modeled as a lightweight single-participant meeting so
    transcripts/history/reconnect all reuse the meeting machinery.
    """
    from app.deps import flag_enabled
    if not await flag_enabled(db, "voice_translation", principal.org_id):
        from app.errors import FeatureDisabledError
        raise FeatureDisabledError("Voice translation is disabled.")
    for lang in body.hear_langs:
        from app.services.translation_service import validate_pair
        await validate_pair(db, "en", lang, need_realtime=True)
    meeting = M.Meeting(
        org_id=principal.org_id, title="Voice session",
        mode="ws", room_name=f"voice-{uuid.uuid4().hex[:10]}",
        status="live", started_at=utcnow(), created_by=principal.user_id,
        settings_json={"kind": "voice_session", "hear_langs": body.hear_langs})
    db.add(meeting)
    await db.flush()
    p, pref, session_key = await meeting_service.join_meeting(
        db, meeting, user_id=principal.user_id,
        display_name=(principal.user.name if principal.user else "API"),
        speak_lang=body.speak_lang, hear_lang=body.hear_langs[0],
        audio_mode=body.audio_mode)
    ticket = create_session_ticket(meeting.room_name, str(p.id))
    return {
        "session_id": str(meeting.id),
        "participant_id": str(p.id),
        "ws_url": f"/ws/realtime?ticket={ticket}",
        "hear_langs": body.hear_langs,
        "protocol_version": 1,
    }
