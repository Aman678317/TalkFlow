"""Meetings router: create/join/participants/preferences/transcript/tokens
(PDD §12, §20, §33). Also standalone voice sessions (PDD §19 API product).
"""
from __future__ import annotations

import contextlib
import logging
import uuid

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import models as M
from app.db.base import utcnow
from app.db.session import get_db
from app.deps import Principal, get_principal_optional, require_org_user, require_scope
from app.errors import AuthenticationError, NotFoundError, ValidationError
from app.realtime import livekit_bridge
from app.realtime.protocol import ServerEventType
from app.schemas import (
    JoinMeetingRequest, JoinMeetingResponse, JoinTicketRequest, JoinTicketResponse,
    MeetingCreate, MeetingDetailOut, MeetingOut, ParticipantFullOut, ParticipantOut,
    PreferenceOut, PreferenceUpdate, PreferenceUpdate as _PrefUpd,
    TranscriptSegmentOut, VoiceSessionCreate,
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
        hear_lang=body.hear_lang,
        tenant_private_only=body.tenant_private_only)
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
    return [_meeting_out(m) for m in res.scalars().all()]


def _meeting_out(meeting: M.Meeting) -> MeetingOut:
    """Serialize a meeting with the derived fields the web client expects."""
    out = MeetingOut.model_validate(meeting)
    out.transport = meeting.mode
    out.has_summary = bool(meeting.summary_json)
    return out


async def _detail(db: AsyncSession, meeting: M.Meeting,
                  principal: Principal | None = None) -> MeetingDetailOut:
    participants = await meeting_service.list_participants(db, meeting.id)
    base = MeetingDetailOut.model_validate(meeting)
    base.transport = meeting.mode
    base.has_summary = bool(meeting.summary_json)
    if meeting.mode == "livekit" and livekit_bridge.enabled():
        base.livekit_url = livekit_bridge.public_url()
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
        audio_mode=body.audio_mode, session_key=body.session_key,
        as_guest=body.as_guest)

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


TICKET_TTL_S = 120


@router.post("/meetings/{meeting_id}/join-ticket", response_model=JoinTicketResponse)
async def meeting_join_ticket(meeting_id: uuid.UUID,
                              body: JoinTicketRequest,
                              principal: Principal | None = Depends(get_principal_optional),
                              db: AsyncSession = Depends(get_db)):
    """Mint a signed, single-use, 120s realtime ticket (roadmap Phase 4 task 1).

    Guests present the server-issued `session_key` from their /join response —
    the only guest credential, and it never travels in a WS URL. Authenticated
    callers re-mint for the seat they joined. The WebSocket layer accepts
    tickets (and member JWTs) only; static join tokens are gone.
    """
    meeting = await db.get(M.Meeting, meeting_id)
    if meeting is None:
        raise NotFoundError("Meeting not found.")
    if meeting.status not in ("scheduled", "live"):
        raise ValidationError("Meeting is not joinable.",
                              details={"status": meeting.status})
    participant: M.Participant | None = None
    if body.session_key:
        res = await db.execute(
            select(M.Participant)
            .join(M.AudioSession, M.AudioSession.participant_id == M.Participant.id)
            .where(M.AudioSession.session_key == body.session_key,
                   M.Participant.meeting_id == meeting.id))
        participant = res.scalars().first()
        if participant is None:
            raise AuthenticationError("Invalid or expired session key.")
    else:
        if principal is None or not principal.user_id:
            raise AuthenticationError("Authentication or session key required.")
        participants = await meeting_service.list_participants(db, meeting.id)
        participant = next((p for p, _ in participants
                            if p.user_id == principal.user_id), None)
        if participant is None:
            raise NotFoundError("Join the meeting first.")
    ticket = create_session_ticket(meeting.room_name, str(participant.id),
                                   ttl_s=TICKET_TTL_S)
    return JoinTicketResponse(
        ticket=ticket, ws_url=f"/ws/realtime?ticket={ticket}",
        participant_id=participant.id, expires_in=TICKET_TTL_S)


@router.post("/meetings/{meeting_id}/leave", status_code=204)
async def leave_meeting(
    meeting_id: uuid.UUID,
    request: Request,
    body: dict = Body(default_factory=dict),
    principal: Principal | None = Depends(get_principal_optional),
    db: AsyncSession = Depends(get_db),
):
    """Cleanly mark participant as left and broadcast participant.left event.

    Phase 3: a supplied participant_id is only honored when it belongs to THIS
    meeting and the caller is authorized (the participant themself, a member of
    the meeting's org, or an unauthenticated guest holding the join capability).
    Foreign meetings/orgs get a uniform 404 — never a 403 or a silent cross-
    tenant write (previously any participant_id from any meeting was accepted).
    """
    meeting = await db.get(M.Meeting, meeting_id)
    if meeting is None:
        raise NotFoundError("Meeting not found.")

    caller_org_member = bool(
        principal and principal.org_id and str(meeting.org_id) == str(principal.org_id)
    )
    own_row: M.Participant | None = None
    if principal and principal.user_id:
        res = await db.execute(
            select(M.Participant).where(
                M.Participant.meeting_id == meeting_id,
                M.Participant.user_id == principal.user_id,
                M.Participant.status == "joined",
            )
        )
        own_row = res.scalars().first()

    p_id_str = body.get("participant_id")
    if not p_id_str:
        p_id_str = request.headers.get("x-participant-id") or request.query_params.get("participant_id")

    p_uuid: uuid.UUID | None = None
    if p_id_str:
        with contextlib.suppress(Exception):
            p_uuid = uuid.UUID(str(p_id_str))

    if p_uuid is not None:
        target = await db.get(M.Participant, p_uuid)
        is_self = bool(principal and principal.user_id and target and target.user_id == principal.user_id)
        is_participant = own_row is not None
        if target is None or target.meeting_id != meeting_id:
            # Unknown or foreign-meeting participant: uniform 404, no action.
            raise NotFoundError("Meeting not found.")
        if not (principal is None or caller_org_member or is_self or is_participant):
            raise NotFoundError("Meeting not found.")
    elif own_row is not None:
        p_uuid = own_row.id
    else:
        # Cannot identify who is leaving (no participant_id, no joined row).
        raise NotFoundError("Meeting not found.")

    if p_uuid:
        await meeting_service.leave_participant(db, p_uuid)
        from app.realtime.session_manager import manager
        session = manager.get_session_for_meeting(meeting_id)
        if session:
            manager.remove_participant(session, p_uuid)
            with contextlib.suppress(Exception):
                await manager.broadcast(
                    session,
                    ServerEventType.PARTICIPANT_LEFT,
                    {"participant_id": str(p_uuid)},
                    to=[v for v in session.participants.values() if v.connected],
                )


DEFAULT_ICE_SERVERS = [
    {"urls": [
        "stun:stun.l.google.com:19302",
        "stun:stun1.l.google.com:19302",
    ]},
]


@router.get("/meetings/{meeting_id}/ice-servers")
async def meeting_ice_servers(
    meeting_id: uuid.UUID,
    request: Request,
    principal: Principal | None = Depends(get_principal_optional),
    db: AsyncSession = Depends(get_db),
):
    """RTC ICE servers for the P2P mesh (WS-transport meetings).

    `RTCPeerConnection.iceServers` is a browser-only knob: people joined to the
    room need reachable STUN/TURN, everyone else must not. STUN-only defaults
    apply when the deployment has not configured a TURN edge (which symmetric
    NAT and most mobile-carrier networks require for any media to flow).
    """
    meeting = await db.get(M.Meeting, meeting_id)
    if meeting is None:
        raise NotFoundError("Meeting not found.")

    participants = await meeting_service.list_participants(db, meeting.id)
    is_org_member = bool(principal and principal.org_id and principal.org_id == meeting.org_id)
    is_participant = bool(
        principal and principal.user_id
        and any(p.user_id == principal.user_id for p, _ in participants)
    )
    p_header = request.headers.get("x-participant-id") or request.query_params.get("participant_id")
    is_guest = False
    if p_header:
        with contextlib.suppress(ValueError):
            p_uuid = uuid.UUID(p_header)
            is_guest = any(p.id == p_uuid for p, _ in participants)

    if not (is_org_member or is_participant or is_guest):
        raise NotFoundError("Meeting not found.")

    import json as _json

    servers: list[dict] | None = None
    raw = (settings.webrtc_ice_servers_json or "").strip()
    if raw:
        try:
            parsed = _json.loads(raw)
            if isinstance(parsed, list) and parsed:
                servers = [s for s in parsed if isinstance(s, dict) and s.get("urls")]
        except Exception:
            log.warning("webrtc_ice_servers_json is set but not valid JSON; using STUN defaults")
    return {"ice_servers": servers or DEFAULT_ICE_SERVERS}


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


@router.post("/meetings/{meeting_id}/media-token", response_model=dict)
async def meeting_media_token(meeting_id: uuid.UUID,
                              participant_id: uuid.UUID = Query(...),
                              body: dict = Body(default_factory=dict),
                              principal: Principal | None = Depends(get_principal_optional),
                              db: AsyncSession = Depends(get_db)):
    """LiveKit SFU credentials for an already-joined participant.

    `/tokens` hands out a websocket ticket; the browser media layer instead
    needs the {url, token} pair that livekit-client connects with.

    Authorized callers: an org member minting for their own seat (or a
    manage_members holder), or a guest presenting the seat's `session_key` —
    the same guest credential /join-ticket accepts. Guests joined from a
    shared link have no organization, so without the seat path their only
    media credential ever minted is the one-shot token inside the /join
    response, and any mid-call reconnect strands them.
    """
    if not livekit_bridge.enabled():
        raise ValidationError(
            "Video calling is not configured for this server.",
            details={"code": "media_transport_unavailable"})
    meeting = await db.get(M.Meeting, meeting_id)
    if meeting is None:
        raise NotFoundError("Meeting not found.")
    if meeting.mode != "livekit":
        raise ValidationError(
            "This meeting runs on the websocket transport.",
            details={"code": "media_transport_unavailable", "mode": meeting.mode})

    session_key = (body or {}).get("session_key")
    mine: M.Participant | None = None
    if not principal or not principal.org_id:
        # Guest seat path: the session key is the credential, and it mints
        # ONLY for the seat it binds — never for an arbitrary participant_id.
        if not session_key:
            raise AuthenticationError("Authentication or session key required.")
        res = await db.execute(
            select(M.Participant)
            .join(M.AudioSession, M.AudioSession.participant_id == M.Participant.id)
            .where(M.AudioSession.session_key == session_key,
                   M.Participant.meeting_id == meeting.id))
        mine = res.scalars().first()
        if mine is None or mine.id != participant_id:
            raise AuthenticationError("Invalid or expired session key.")
    else:
        await _meeting_or_404(db, meeting_id, principal)
        participants = await meeting_service.list_participants(db, meeting.id)
        mine = next((p for p, _ in participants if p.id == participant_id), None)
        if mine is None:
            raise NotFoundError("Join the meeting first.")
        # Mint only for the caller's own identity unless they manage members;
        # otherwise any org user could join the room as someone else.
        if not (principal.user_id and mine.user_id == principal.user_id):
            principal.require("manage_members")
    credentials = livekit_bridge.join_token(
        meeting.room_name, mine.livekit_identity or str(mine.id),
        mine.display_name,
        {"meeting_id": str(meeting.id), "participant_id": str(mine.id)})
    if credentials is None:
        raise ValidationError("Video calling is not configured for this server.",
                              details={"code": "media_transport_unavailable"})
    return {"url": credentials["url"], "room": meeting.room_name,
            "identity": mine.livekit_identity or str(mine.id),
            "token": credentials["token"]}


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
