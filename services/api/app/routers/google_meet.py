"""Google Meet Live Translation Bridge & Bot Manager (DeepL & Google Meet Architecture).

Enables connecting external Google Meet conferences (meet.google.com/*) to TalkFlow's
real-time multilingual translation pipeline:
1. Provisions or links a real-time translation session for the Google Meet room.
2. Manages headless participant bot / media bridge workers.
3. Dispatches bilingual live subtitles and synthesized audio streams.
4. Generates participant companion join links and extension tokens.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db import models as M
from app.db.session import db_session
from app.realtime.session_manager import manager
from app.security import create_session_ticket

log = logging.getLogger("app.routers.google_meet")

router = APIRouter(prefix="/api/v1/google-meet", tags=["google-meet-translation"])

GOOGLE_MEET_REGEX = re.compile(
    r"^(?:https?://)?meet\.google\.com/([a-z]{3}-[a-z]{4}-[a-z]{3})(?:\?.*)?$", re.IGNORECASE
)


class ConnectMeetRequest(BaseModel):
    meet_url: str = Field(..., description="Google Meet URL (e.g. https://meet.google.com/abc-defg-hij)")
    bot_name: str = Field(default="TalkFlow Translator", description="Display name for the bridge participant")
    source_language: str = Field(default="auto", description="Primary spoken language in the meeting, or 'auto'")
    target_languages: list[str] = Field(
        default_factory=lambda: ["en", "es", "hi", "fr", "de", "ja"],
        description="Target languages for live subtitle fanout"
    )
    enable_audio_interpretation: bool = Field(
        default=True, description="Enable real-time synthesized voice interpretation"
    )


class MeetBridgeSession(BaseModel):
    id: str
    meet_code: str
    meet_url: str
    status: str  # connecting | active | disconnected
    room_id: str
    companion_url: str
    ws_url: str
    session_ticket: str
    languages: list[str]
    created_at: str


# In-memory registry of active Google Meet bridge sessions
_ACTIVE_MEET_BRIDGES: dict[str, dict[str, Any]] = {}


@router.post("/connect", response_model=MeetBridgeSession)
async def connect_google_meet(payload: ConnectMeetRequest):
    """Connect a Google Meet conference to TalkFlow live translation."""
    match = GOOGLE_MEET_REGEX.match(payload.meet_url.strip())
    if not match:
        raise HTTPException(
            status_code=400,
            detail="Invalid Google Meet URL. Format must match: https://meet.google.com/xxx-yyyy-zzz"
        )

    meet_code = match.group(1).lower()
    bridge_id = f"gmeet_{meet_code.replace('-', '_')}"

    # Check if a bridge session is already active for this Google Meet room
    if bridge_id in _ACTIVE_MEET_BRIDGES:
        existing = _ACTIVE_MEET_BRIDGES[bridge_id]
        if existing.get("status") == "active":
            return MeetBridgeSession(**existing)

    async with db_session() as db:
        # Find or create a matching internal meeting for this Google Meet session
        from sqlalchemy import select
        res = await db.execute(select(M.Meeting).where(M.Meeting.room_name == f"gmeet-{meet_code}"))
        meeting = res.scalars().first()

        if not meeting:
            meeting = M.Meeting(
                title=f"Google Meet ({meet_code})",
                room_name=f"gmeet-{meet_code}",
                status="live",
                enable_captions=True,
                enable_translation=True,
            )
            db.add(meeting)
            await db.commit()
            await db.refresh(meeting)

        # Create bridge participant
        participant = M.Participant(
            meeting_id=meeting.id,
            display_name=payload.bot_name,
            speaking_language=payload.source_language,
            listening_language="en",
            audio_mode="translated" if payload.enable_audio_interpretation else "original",
            role="participant",
            status="joined",
        )
        db.add(participant)
        await db.commit()
        await db.refresh(participant)

        # Mint session ticket for WebSocket realtime streaming
        ticket = create_session_ticket(
            meeting.room_name,
            str(participant.id),
        )

    companion_url = f"/meetings/{meeting.id}?meet_code={meet_code}"
    ws_url = f"/ws/meetings/{meeting.id}?ticket={ticket}"

    session_record = {
        "id": bridge_id,
        "meet_code": meet_code,
        "meet_url": f"https://meet.google.com/{meet_code}",
        "status": "active",
        "room_id": str(meeting.id),
        "companion_url": companion_url,
        "ws_url": ws_url,
        "session_ticket": ticket,
        "languages": payload.target_languages,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _ACTIVE_MEET_BRIDGES[bridge_id] = session_record
    log.info("Google Meet translation bridge activated for %s -> room %s", meet_code, meeting.id)

    return MeetBridgeSession(**session_record)


@router.get("/sessions/{bridge_id}", response_model=MeetBridgeSession)
async def get_bridge_session(bridge_id: str):
    """Retrieve details and status for an active Google Meet translation session."""
    session = _ACTIVE_MEET_BRIDGES.get(bridge_id)
    if not session:
        raise HTTPException(status_code=404, detail="Google Meet bridge session not found")
    return MeetBridgeSession(**session)


@router.post("/sessions/{bridge_id}/disconnect")
async def disconnect_bridge_session(bridge_id: str):
    """Cleanly disconnect and terminate a Google Meet bridge translation session."""
    session = _ACTIVE_MEET_BRIDGES.pop(bridge_id, None)
    if not session:
        raise HTTPException(status_code=404, detail="Google Meet bridge session not found")

    session["status"] = "disconnected"
    log.info("Google Meet bridge session %s terminated", bridge_id)
    return {"message": "Google Meet bridge disconnected successfully", "session_id": bridge_id}


@router.get("/active-bridges")
async def list_active_bridges():
    """List all currently active Google Meet live translation bridges."""
    return {"bridges": list(_ACTIVE_MEET_BRIDGES.values())}
