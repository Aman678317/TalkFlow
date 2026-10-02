"""Meeting lifecycle service: create/join/end, transcript queries, sequence allocation,
participant preference updates, summary attachment. Control-plane operations only —
realtime media state lives in the hub."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from globaltalk.core.errors import NotFoundError, ValidationError
from globaltalk.models import (ChatMessage, Meeting, Participant, ParticipantPreference,
                               TranslationSegment, TranscriptSegment)


def create_meeting(db: Session, *, org_id: str, user_id: str, title: str,
                   settings_map: dict | None = None) -> Meeting:
    if not title.strip():
        raise ValidationError("Meeting title is required")
    room = f"gt-{secrets.token_hex(6)}"
    meeting = Meeting(org_id=org_id, title=title.strip()[:200], created_by=user_id,
                      room_name=room, join_token=secrets.token_urlsafe(24),
                      status="scheduled", settings=settings_map or {})
    db.add(meeting)
    db.commit()
    return meeting


def next_segment_sequence(db: Session, meeting_id: str) -> int:
    cur = (db.query(func.max(TranscriptSegment.sequence))
           .filter(TranscriptSegment.meeting_id == meeting_id).scalar())
    return (cur or 0) + 1


def next_chat_sequence(db: Session, meeting_id: str) -> int:
    cur = (db.query(func.max(ChatMessage.sequence))
           .filter(ChatMessage.meeting_id == meeting_id).scalar())
    return (cur or 0) + 1


def get_transcript(db: Session, meeting_id: str, *, language: str | None = None,
                   participant_id: str | None = None, q: str | None = None,
                   limit: int = 500) -> list[dict]:
    query = (db.query(TranscriptSegment, Participant)
             .join(Participant, Participant.id == TranscriptSegment.participant_id)
             .filter(TranscriptSegment.meeting_id == meeting_id,
                     TranscriptSegment.is_final.is_(True)))
    if language:
        query = query.filter(TranscriptSegment.language == language)
    if participant_id:
        query = query.filter(TranscriptSegment.participant_id == participant_id)
    if q:
        query = query.filter(TranscriptSegment.text.ilike(f"%{q}%"))
    rows = query.order_by(TranscriptSegment.sequence.asc()).limit(limit).all()
    out = []
    seg_ids = [r[0].id for r in rows]
    translations: dict[str, list[TranslationSegment]] = {}
    if seg_ids:
        for t in (db.query(TranslationSegment)
                  .filter(TranslationSegment.source_segment_id.in_(seg_ids)).all()):
            translations.setdefault(t.source_segment_id, []).append(t)
    for seg, part in rows:
        out.append({
            "id": seg.id, "sequence": seg.sequence, "speaker": part.display_name,
            "participant_id": seg.participant_id, "language": seg.language, "text": seg.text,
            "confidence": seg.confidence, "stt_provider": seg.stt_provider,
            "stt_model": seg.stt_model, "started_at_ms": seg.started_at_ms,
            "ended_at_ms": seg.ended_at_ms, "created_at": seg.created_at.isoformat(),
            "latency": seg.latency or {}, "correction_status": seg.correction_status,
            "translations": [{
                "id": t.id, "target_language": t.target_language, "text": t.text,
                "provider": t.provider, "model": t.model,
                "quality_flags": t.quality_flags or [], "tts_audio_key": t.tts_audio_key,
            } for t in translations.get(seg.id, [])],
        })
    return out


def end_meeting(db: Session, meeting_id: str) -> Meeting:
    m = db.get(Meeting, meeting_id)
    if not m:
        raise NotFoundError("Meeting not found")
    m.status = "ended"
    m.ended_at = datetime.now(timezone.utc)
    for p in db.query(Participant).filter(Participant.meeting_id == meeting_id,
                                          Participant.status == "joined").all():
        p.status = "left"
        p.left_at = m.ended_at
    db.commit()
    return m


def update_preferences(db: Session, participant_id: str, **changes) -> ParticipantPreference:
    pref = (db.query(ParticipantPreference)
            .filter(ParticipantPreference.participant_id == participant_id).first())
    if not pref:
        pref = ParticipantPreference(participant_id=participant_id)
        db.add(pref)
    for k in ("speaking_language", "listening_language", "audio_mode", "caption_mode",
              "latency_mode"):
        if k in changes and changes[k] is not None:
            setattr(pref, k, changes[k])
    db.commit()
    return pref


def stable_transcript_text(db: Session, meeting_id: str) -> str:
    """Canonical stable context for AI tasks: final human-source segments only.
    Derivative artifacts (translations, summaries) are NEVER fed back as source."""
    rows = (db.query(TranscriptSegment, Participant)
            .join(Participant, Participant.id == TranscriptSegment.participant_id)
            .filter(TranscriptSegment.meeting_id == meeting_id,
                    TranscriptSegment.is_final.is_(True))
            .order_by(TranscriptSegment.sequence.asc()).all())
    lines = []
    for seg, part in rows:
        lines.append(f"{part.display_name} ({seg.language}): {seg.text}")
    return "\n".join(lines)
