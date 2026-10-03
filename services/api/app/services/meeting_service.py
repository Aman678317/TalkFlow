"""Meeting service: meetings, participants, preferences, LiveKit tokens.

Canonical routing rule lives here (PDD §12): routing key =
(participant_id, hear_lang); translation fan-out key = (segment_id, target_lang).
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import models as M
from app.db.base import utcnow
from app.errors import ConflictError, NotFoundError
from app.services import audit_service

log = logging.getLogger("app.meetings")


def _room_name(title: str) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in title.lower()).strip("-")[:40]
    return f"{slug or 'meeting'}-{secrets.token_hex(3)}"


async def create_meeting(db: AsyncSession, *, org_id: uuid.UUID,
                         created_by: uuid.UUID | None, title: str,
                         mode: str, speak_lang: str, hear_lang: str,
                         project_id: uuid.UUID | None = None) -> tuple[M.Meeting, M.Participant]:
    meeting = M.Meeting(
        org_id=org_id, project_id=project_id, title=title, mode=mode,
        room_name=_room_name(title), created_by=created_by, status="scheduled",
        settings_json={"default_speak_lang": speak_lang, "default_hear_lang": hear_lang},
    )
    db.add(meeting)
    await db.flush()
    participant, _pref = await _add_participant(
        db, meeting, user_id=created_by, display_name="", role="host",
        speak_lang=speak_lang, hear_lang=hear_lang)
    await audit_service.record(db, action="meeting.created", org_id=org_id,
                               actor_id=created_by, resource_type="meeting",
                               resource_id=str(meeting.id))
    await db.commit()
    return meeting, participant


async def _add_participant(db: AsyncSession, meeting: M.Meeting, *,
                           user_id: uuid.UUID | None, display_name: str,
                           role: str, speak_lang: str, hear_lang: str,
                           guest_key: str = "") -> tuple[M.Participant, M.ParticipantPreference]:
    if not guest_key:
        guest_key = "" if user_id else secrets.token_hex(8)
    p = M.Participant(
        meeting_id=meeting.id, user_id=user_id, guest_key=guest_key,
        display_name=display_name, role=role, status="invited",
        livekit_identity=f"{user_id or guest_key}"[:120],
    )
    db.add(p)
    await db.flush()
    pref = M.ParticipantPreference(
        participant_id=p.id, meeting_id=meeting.id, speak_lang=speak_lang,
        hear_lang=hear_lang, audio_mode="translated", captions_enabled=True)
    db.add(pref)
    return p, pref


async def join_meeting(db: AsyncSession, meeting: M.Meeting, *,
                       user_id: uuid.UUID | None, display_name: str,
                       speak_lang: str, hear_lang: str, audio_mode: str,
                       guest_key: str = "") -> tuple[M.Participant, M.ParticipantPreference, str]:
    """Idempotent join: same user/guest_key reuses the participant row.

    Lookup priority: guest_key (when provided) wins over user_id so a single
    authenticated user can open additional guest seats (multi-browser demo,
    QA personas) without hijacking their own participant row.
    """
    p = None
    if guest_key:
        res = await db.execute(select(M.Participant).where(
            M.Participant.meeting_id == meeting.id,
            M.Participant.guest_key == guest_key))
        p = res.scalars().first()
    if p is None and user_id and not guest_key:
        res = await db.execute(select(M.Participant).where(
            M.Participant.meeting_id == meeting.id,
            M.Participant.user_id == user_id))
        p = res.scalars().first()
    if p is None:
        p, pref = await _add_participant(db, meeting, user_id=user_id,
                                         display_name=display_name, role="member",
                                         speak_lang=speak_lang, hear_lang=hear_lang,
                                         guest_key=guest_key)
    else:
        pref = (await db.execute(select(M.ParticipantPreference).where(
            M.ParticipantPreference.participant_id == p.id))).scalars().first()
        if pref is None:
            pref = M.ParticipantPreference(
                participant_id=p.id, meeting_id=meeting.id,
                speak_lang=speak_lang, hear_lang=hear_lang,
                audio_mode="translated", captions_enabled=True)
            db.add(pref)
        if not display_name and p.user_id:
            u = await db.get(M.User, p.user_id)
            display_name = (u.name or u.email.split("@")[0]) if u else ""
        if display_name:
            p.display_name = display_name
    p.status = "joined"
    p.joined_at = utcnow()
    p.left_at = None
    pref.speak_lang = speak_lang
    pref.hear_lang = hear_lang
    if audio_mode == "both":
        audio_mode = "mixed"
    elif audio_mode not in ("original", "translated", "mixed", "captions_only"):
        audio_mode = "translated"
    pref.audio_mode = audio_mode
    if meeting.status == "scheduled":
        meeting.status = "live"
        meeting.started_at = utcnow()
    session_key = secrets.token_urlsafe(24)
    db.add(M.AudioSession(
        meeting_id=meeting.id, participant_id=p.id, session_key=session_key,
        transport="livekit" if meeting.mode == "livekit" else "ws",
        status="active", started_at=utcnow()))
    await db.commit()
    return p, pref, session_key


async def leave_participant(db: AsyncSession, participant_id: uuid.UUID) -> None:
    p = await db.get(M.Participant, participant_id)
    if p:
        p.status = "left"
        p.left_at = utcnow()
        await db.commit()


async def update_preference(db: AsyncSession, participant_id: uuid.UUID, *,
                            speak_lang: str | None, hear_lang: str | None,
                            audio_mode: str | None,
                            captions_enabled: bool | None) -> M.ParticipantPreference:
    pref = (await db.execute(select(M.ParticipantPreference).where(
        M.ParticipantPreference.participant_id == participant_id))).scalars().first()
    if pref is None:
        raise NotFoundError("Participant preference not found.")
    if speak_lang is not None:
        pref.speak_lang = speak_lang
    if hear_lang is not None:
        pref.hear_lang = hear_lang
    if audio_mode is not None:
        pref.audio_mode = audio_mode
    if captions_enabled is not None:
        pref.captions_enabled = captions_enabled
    await db.commit()
    return pref


async def get_meeting_for_org(db: AsyncSession, meeting_id: uuid.UUID,
                              org_id: uuid.UUID) -> M.Meeting:
    meeting = await db.get(M.Meeting, meeting_id)
    if meeting is None or meeting.org_id != org_id:
        # uniform 404 to avoid cross-tenant existence leaks
        raise NotFoundError("Meeting not found.")
    return meeting


async def list_participants(db: AsyncSession, meeting_id: uuid.UUID):
    res = await db.execute(select(M.Participant).where(
        M.Participant.meeting_id == meeting_id).order_by(M.Participant.created_at))
    participants = res.scalars().all()
    out = []
    for p in participants:
        pref = (await db.execute(select(M.ParticipantPreference).where(
            M.ParticipantPreference.participant_id == p.id))).scalars().first()
        out.append((p, pref))
    return out


async def end_meeting(db: AsyncSession, meeting: M.Meeting) -> None:
    meeting.status = "ended"
    meeting.ended_at = utcnow()
    await db.commit()


def livekit_join_token(room_name: str, identity: str, name: str,
                       metadata: dict) -> dict | None:
    """Mint a short-lived LiveKit access token server-side (secrets never leave
    the backend). Returns None when LiveKit is disabled."""
    if not settings.livekit_enabled:
        return None
    try:
        from livekit import api as lk_api  # type: ignore
    except ImportError:
        # fallback: hand-rolled JWT (LiveKit tokens are standard JWTs)
        return _manual_livekit_token(room_name, identity, name, metadata)
    import time as _t
    from datetime import timedelta as _td
    at = lk_api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
    at = at.with_identity(identity).with_name(name).with_metadata(
        __import__("json").dumps(metadata)
    ).with_grants(lk_api.VideoGrants(room_join=True, room=room_name))  # type: ignore[attr-defined]
    at.ttl = _td(hours=6)
    return {"url": settings.livekit_url, "token": at.to_jwt()}


def _manual_livekit_token(room_name: str, identity: str, name: str,
                          metadata: dict) -> dict:
    import json
    import time as _time
    from app.security import create_token
    import jwt as pyjwt
    now = int(_time.time())
    payload = {
        "iss": settings.livekit_api_key,
        "sub": identity,
        "name": name,
        "metadata": json.dumps(metadata),
        "nbf": now - 10,
        "exp": now + 6 * 3600,
        "video": {"roomJoin": True, "room": room_name},
        "jti": secrets.token_hex(8),
    }
    token = pyjwt.encode(payload, settings.livekit_api_secret, algorithm="HS256")
    return {"url": settings.livekit_url, "token": token}
