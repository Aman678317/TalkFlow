"""Phase 4: the room has to say what it keeps, in the numbers it will honour.

The guide asks for "retention and consent behavior appropriate for any stored
media", and a consent notice is only worth its numbers if they come from the
same resolution the deletion job uses. `GET /api/v1/meetings/{id}` now returns
the four windows that `retention_service.sweep()` will apply to that room, so
the lobby can tell a participant what survives the call before they speak —
including a guest, who has no account to inspect afterwards.
"""
from __future__ import annotations

import uuid

import pytest

from app.config import settings
from app.db import models as M
from app.db.session import db_session


async def _policy(kind: str, row_id: str, retention: dict) -> None:
    """Put a policy on the org or the meeting, the way an operator would."""
    async with db_session() as db:
        row = await db.get(getattr(M, kind), uuid.UUID(row_id))
        row.retention_json = retention
        await db.commit()


def _room(services_app_client, user) -> str:
    r = services_app_client.post("/api/v1/meetings", json={"title": "Retention disclosure"},
                                 headers=user["headers"])
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _shown(services_app_client, room: str, headers=None) -> dict:
    r = services_app_client.get(f"/api/v1/meetings/{room}",
                                headers=headers or {})
    assert r.status_code == 200, r.text
    return r.json()["retention"]


def test_the_room_reports_the_windows_it_starts_with(services_app_client, user):
    """A room with no policy of its own says so by naming the deployment's."""
    room = _room(services_app_client, user)

    assert _shown(services_app_client, room, user["headers"]) == {
        "audio_days": settings.retention_audio_days,
        "transcript_days": settings.retention_transcript_days,
        "document_days": settings.retention_document_days,
        "usage_days": settings.retention_usage_days,
    }


@pytest.mark.asyncio
async def test_the_company_shorter_window_is_the_one_shown(services_app_client, user):
    room = _room(services_app_client, user)
    await _policy("Organization", user["org_id"], {"transcript_days": 30,
                                                   "audio_days": 3})

    shown = _shown(services_app_client, room, user["headers"])

    assert shown["transcript_days"] == 30, shown
    assert shown["audio_days"] == 3, shown


@pytest.mark.asyncio
async def test_one_room_can_be_kept_shorter_than_the_rest_of_the_company(
        services_app_client, user):
    """The notice is per room, so the room's own decision is what it reads."""
    room = _room(services_app_client, user)
    await _policy("Organization", user["org_id"], {"transcript_days": 365})
    await _policy("Meeting", room, {"transcript_days": 7, "audio_days": 0})

    shown = _shown(services_app_client, room, user["headers"])

    assert shown["transcript_days"] == 7, shown
    assert shown["audio_days"] == 0, (
        "a room that keeps no audio must say 0, not inherit the company's week")


@pytest.mark.asyncio
async def test_the_guest_joining_by_link_sees_the_same_numbers(
        services_app_client, user):
    """Consent has to reach the person with no account.

    A guest joins on a link, not a login, and they are the one whose voice is
    being kept — a disclosure behind an authenticated call would be read by
    exactly the people who did not need to agree.
    """
    room = _room(services_app_client, user)
    await _policy("Meeting", room, {"transcript_days": 14})

    assert _shown(services_app_client, room) == _shown(
        services_app_client, room, user["headers"])
