"""Meetings: lifecycle, participants & preferences ("I speak / I want to hear"), transcript,
export, AI summary & Q&A, chat history. Realtime itself runs on /ws/meetings/{id}."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from globaltalk.core.audit import audit
from globaltalk.core.config import settings
from globaltalk.core.db import get_db
from globaltalk.core.deps import Principal, get_principal, require_permission
from globaltalk.core.errors import NotFoundError, ValidationError
from globaltalk.models import ChatMessage, Meeting, Participant, ParticipantPreference
from globaltalk.schemas import (MeetingCreate, MeetingOut, ParticipantOut, PreferenceIn,
                                QuestionIn, SummaryOut, TranscriptItem)
from globaltalk.services import assistant as assistant_svc
from globaltalk.services import meetings as meetings_svc
from globaltalk.services.chat import chat_history_with_translations

router = APIRouter(prefix="/meetings", tags=["meetings"])


def _get_meeting(db: Session, meeting_id: str, principal: Principal) -> Meeting:
    m = db.query(Meeting).filter(Meeting.id == meeting_id,
                                 Meeting.org_id == principal.org_id).first()
    if not m:
        # tenant isolation: same 404 for "exists elsewhere" and "does not exist"
        raise NotFoundError("Meeting not found")
    return m


def _out(m: Meeting) -> MeetingOut:
    livekit_url = (settings.livekit_public_url or settings.livekit_url) \
        if settings.livekit_configured else None
    return MeetingOut(id=m.id, title=m.title, status=m.status, room_name=m.room_name,
                      join_token=m.join_token, created_at=m.created_at,
                      started_at=m.started_at, ended_at=m.ended_at,
                      has_summary=bool(m.summary),
                      transport="livekit" if livekit_url else "websocket",
                      livekit_url=livekit_url)


@router.post("", response_model=MeetingOut, status_code=201)
def create_meeting(body: MeetingCreate,
                   principal: Principal = Depends(require_permission("create_meeting")),
                   db: Session = Depends(get_db)):
    m = meetings_svc.create_meeting(db, org_id=principal.org_id,
                                    user_id=principal.user_id or "", title=body.title,
                                    settings_map=body.settings)
    audit(db, "meeting.create", org_id=m.org_id, actor_user_id=principal.user_id,
          resource_type="meeting", resource_id=m.id)
    return _out(m)


@router.get("", response_model=list[MeetingOut])
def list_meetings(principal: Principal = Depends(get_principal),
                  db: Session = Depends(get_db),
                  limit: int = Query(default=50, le=200)):
    rows = (db.query(Meeting).filter(Meeting.org_id == principal.org_id)
            .order_by(Meeting.created_at.desc()).limit(limit).all())
    return [_out(m) for m in rows]


@router.get("/{meeting_id}", response_model=MeetingOut)
def get_meeting(meeting_id: str, principal: Principal = Depends(get_principal),
                db: Session = Depends(get_db)):
    return _out(_get_meeting(db, meeting_id, principal))


@router.post("/{meeting_id}/media-token")
def create_media_token(meeting_id: str, participant_id: str = Query(min_length=1),
                       principal: Principal = Depends(get_principal),
                       db: Session = Depends(get_db)):
    meeting = _get_meeting(db, meeting_id, principal)
    if not settings.livekit_configured:
        raise ValidationError("Video calling is not configured for this server",
                              code="media_transport_unavailable")
    participant = (db.query(Participant)
                   .filter(Participant.id == participant_id,
                           Participant.meeting_id == meeting.id,
                           Participant.status == "joined",
                           Participant.user_id == principal.user_id).first())
    if not participant:
        raise NotFoundError("Active meeting participant not found")
    from services.realtime.livekit_adapter import adapter

    identity = participant.id
    token = adapter.create_participant_token(
        meeting.room_name, identity, participant.display_name,
        metadata={"meeting_id": meeting.id, "participant_id": participant.id,
                  "user_id": principal.user_id},
    )
    return {"url": settings.livekit_public_url or settings.livekit_url,
            "room": meeting.room_name, "identity": identity, "token": token}


@router.post("/{meeting_id}/end", response_model=MeetingOut)
def end_meeting(meeting_id: str,
                principal: Principal = Depends(require_permission("delete_meeting")),
                db: Session = Depends(get_db)):
    _get_meeting(db, meeting_id, principal)
    m = meetings_svc.end_meeting(db, meeting_id)
    audit(db, "meeting.end", org_id=m.org_id, actor_user_id=principal.user_id,
          resource_type="meeting", resource_id=m.id)
    return _out(m)


@router.get("/{meeting_id}/participants", response_model=list[ParticipantOut])
def list_participants(meeting_id: str, principal: Principal = Depends(get_principal),
                      db: Session = Depends(get_db)):
    _get_meeting(db, meeting_id, principal)
    rows = (db.query(Participant).filter(Participant.meeting_id == meeting_id,
                                         Participant.status == "joined")
            .order_by(Participant.joined_at.asc()).all())
    out = []
    for p in rows:
        pref = p.preferences
        out.append(ParticipantOut(id=p.id, display_name=p.display_name, status=p.status,
                                  speaking_language=pref.speaking_language if pref else "AUTO",
                                  listening_language=pref.listening_language if pref else "en",
                                  audio_mode=pref.audio_mode if pref else "translated",
                                  caption_mode=pref.caption_mode if pref else "both"))
    return out


@router.put("/{meeting_id}/participants/{participant_id}/preferences",
            response_model=ParticipantOut)
def update_preferences(meeting_id: str, participant_id: str, body: PreferenceIn,
                       principal: Principal = Depends(get_principal),
                       db: Session = Depends(get_db)):
    _get_meeting(db, meeting_id, principal)
    p = (db.query(Participant)
         .filter(Participant.id == participant_id,
                 Participant.meeting_id == meeting_id).first())
    if not p:
        raise NotFoundError("Participant not found")
    meetings_svc.update_preferences(db, participant_id, **body.model_dump())
    # live update: push into the running session so routing changes immediately
    from globaltalk.realtime.hub import hub
    session = hub.get(meeting_id)
    if session:
        conn = session.participants.get(participant_id)
        if conn:
            conn.speaking_language = body.speaking_language
            conn.listening_language = body.listening_language
            conn.audio_mode = body.audio_mode
            conn.caption_mode = body.caption_mode
            conn.latency_mode = body.latency_mode
    return ParticipantOut(id=p.id, display_name=p.display_name, status=p.status,
                          speaking_language=body.speaking_language,
                          listening_language=body.listening_language,
                          audio_mode=body.audio_mode, caption_mode=body.caption_mode)


@router.get("/{meeting_id}/transcript", response_model=list[TranscriptItem])
def get_transcript(meeting_id: str,
                   principal: Principal = Depends(require_permission("view_transcript")),
                   db: Session = Depends(get_db), language: str | None = None,
                   participant_id: str | None = None, q: str | None = None,
                   limit: int = Query(default=500, le=2000)):
    _get_meeting(db, meeting_id, principal)
    rows = meetings_svc.get_transcript(db, meeting_id, language=language,
                                       participant_id=participant_id, q=q, limit=limit)
    return [TranscriptItem(**r) for r in rows]


@router.get("/{meeting_id}/transcript/export")
def export_transcript(meeting_id: str, fmt: str = Query(default="csv", pattern="^(csv|json)$"),
                      principal: Principal = Depends(require_permission("export_document")),
                      db: Session = Depends(get_db)):
    m = _get_meeting(db, meeting_id, principal)
    rows = meetings_svc.get_transcript(db, meeting_id, limit=5000)
    audit(db, "transcript.export", org_id=m.org_id, actor_user_id=principal.user_id,
          resource_type="meeting", resource_id=m.id, details={"format": fmt, "rows": len(rows)})
    if fmt == "json":
        import json
        return Response(content=json.dumps(rows, ensure_ascii=False, indent=2),
                        media_type="application/json",
                        headers={"content-disposition":
                                 f'attachment; filename="transcript_{meeting_id[:8]}.json"'})
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["sequence", "speaker", "language", "text", "translations"])
    for r in rows:
        tr = "; ".join(f"{t['target_language']}: {t['text']}" for t in r["translations"])
        w.writerow([r["sequence"], r["speaker"], r["language"], r["text"], tr])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"content-disposition":
                             f'attachment; filename="transcript_{meeting_id[:8]}.csv"'})


@router.get("/{meeting_id}/chat")
def get_chat(meeting_id: str, principal: Principal = Depends(get_principal),
             db: Session = Depends(get_db), listening_language: str = "en"):
    _get_meeting(db, meeting_id, principal)
    return chat_history_with_translations(db, meeting_id, listening_language)


@router.post("/{meeting_id}/summary", response_model=SummaryOut)
def build_summary(meeting_id: str,
                  principal: Principal = Depends(require_permission("use_assistant")),
                  db: Session = Depends(get_db)):
    _get_meeting(db, meeting_id, principal)
    result = assistant_svc.build_summary(db, meeting_id)
    audit(db, "assistant.summary", org_id=principal.org_id, actor_user_id=principal.user_id,
          resource_type="meeting", resource_id=meeting_id,
          details={"method": result.get("method")})
    return SummaryOut(**result)


@router.get("/{meeting_id}/summary", response_model=SummaryOut | None)
def get_summary(meeting_id: str, principal: Principal = Depends(get_principal),
                db: Session = Depends(get_db)):
    m = _get_meeting(db, meeting_id, principal)
    return SummaryOut(**m.summary) if m.summary else None


@router.post("/{meeting_id}/ask")
def ask_meeting(meeting_id: str, body: QuestionIn,
                principal: Principal = Depends(require_permission("use_assistant")),
                db: Session = Depends(get_db)):
    _get_meeting(db, meeting_id, principal)
    return assistant_svc.answer_question(db, meeting_id, body.question)
