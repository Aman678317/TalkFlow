"""Phase 4: retention has to remove the media, not promise to.

The guide asks for "retention and consent behavior appropriate for any stored
media", and the repository has had the shape of that for a long time: a
`retention_service.sweep()` called from an hourly loop, four
`retention_*_days` settings, and a `policy_for()` that lets an organization
keep things for less time than the deployment default.

Three of those four pieces were decoration.

* **Nothing deletes transcripts.** `retention_transcript_days` (365) is read by
  `policy_for()`, and `policy_for()` has no caller anywhere in the repository.
  `sweep()` removes audio objects, expired documents, usage rows and tokens —
  the sentences people spoke stay forever.
* **Nothing deletes the audio the meeting actually kept.** The pipeline stores a
  WAV against `TranscriptSegment.audio_object_key`, and `sweep()` only looks at
  `AudioSession.audio_object_key`, a column no code in this repository has ever
  written. So the sweep's first step selects rows that cannot exist, while the
  recorded voices sit in storage past the seven days the setting claims.
* **An organization's shorter window is not a thing the code can express.** The
  policy is per-organization, the sweep is one global pass.

These tests pin the four behaviours that follow from fixing that, at the real
database, with the real policy resolver and a fake object store so the assertion
is about which keys the sweep asked to have deleted.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db import models as M
from app.db.base import utcnow
from app.db.session import db_session
from app.services import retention_service as R

SPOKEN = "यह वाक्य रिकॉर्ड किया गया था"


class FakeStorage:
    """Records the keys a caller asked to have removed."""

    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def delete(self, key: str) -> None:
        self.deleted.append(key)


@pytest.fixture
def storage(monkeypatch) -> FakeStorage:
    fake = FakeStorage()
    monkeypatch.setattr(R, "storage", lambda: fake)
    return fake


async def _room(*, org_id=None, room=None, meeting_retention=None,
                org_retention=None) -> uuid.UUID:
    """One org, one meeting, and whatever policy those two declare."""
    async with db_session() as db:
        if org_id is None:
            org = M.Organization(name=f"Org {uuid.uuid4().hex[:6]}",
                                 slug=f"o-{uuid.uuid4().hex[:8]}",
                                 retention_json=org_retention or {})
            db.add(org)
            await db.commit()
            org_id = org.id
        meeting = M.Meeting(
            org_id=org_id, title="Retention probe", mode="ws",
            room_name=room or f"room-{uuid.uuid4().hex[:10]}",
            status="ended", retention_json=meeting_retention or {})
        db.add(meeting)
        await db.commit()
        return meeting.id


async def _caption(meeting_id: uuid.UUID, *, age_days: int,
                   audio_key: str | None = None, translated: bool = True,
                   org_id: uuid.UUID | None = None) -> uuid.UUID:
    async with db_session() as db:
        from sqlalchemy import func
        last = (await db.execute(
            select(func.coalesce(func.max(M.TranscriptSegment.seq), 0))
            .where(M.TranscriptSegment.meeting_id == meeting_id))).scalar() or 0
        segment = M.TranscriptSegment(
            meeting_id=meeting_id, seq=last + 1,
            speaker_name="Aman", source_lang="hi", source_text=SPOKEN,
            is_final=True, audio_object_key=audio_key,
            created_at=utcnow() - timedelta(days=age_days))
        db.add(segment)
        await db.flush()
        if translated:
            db.add(M.TranslationSegment(
                segment_id=segment.id, meeting_id=meeting_id, org_id=org_id,
                product="realtime", source_lang="hi", target_lang="en",
                source_text=SPOKEN, target_text="This sentence was recorded",
                created_at=segment.created_at))
        await db.commit()
        return segment.id


async def _exists(model, row_id: uuid.UUID) -> bool:
    async with db_session() as db:
        return (await db.get(model, row_id)) is not None


async def _audio_key(row_id: uuid.UUID) -> str | None:
    async with db_session() as db:
        segment = await db.get(M.TranscriptSegment, row_id)
        return segment.audio_object_key if segment else None


# --------------------------------------------------------------------------- #
# the window the settings already promise
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_a_caption_past_its_window_is_gone(services_app_client, storage):
    """365 days is a promise, and a sweep that ignores it is not a sweep.

    The derived translation goes with the sentence it translates: it is the same
    words in another language, and keeping it would keep the leak.
    """
    meeting_id = await _room()
    async with db_session() as db:
        org_id = (await db.get(M.Meeting, meeting_id)).org_id
    old = await _caption(meeting_id, age_days=400, translated=True, org_id=org_id)
    glossary_id = await _translation_id(old)

    await _sweep()

    assert not await _exists(M.TranscriptSegment, old), (
        "a transcript older than retention_transcript_days survived the sweep")
    assert not await _exists(M.TranslationSegment, glossary_id), (
        "the translation outlived the sentence it was made from")


@pytest.mark.asyncio
async def test_a_caption_inside_its_window_survives(services_app_client, storage):
    """The other half of a retention rule is that it is not immediate.

    A sweep that deleted everything would pass the test above; summaries and
    participant history depend on this row still being there.
    """
    meeting_id = await _room()
    recent = await _caption(meeting_id, age_days=30)

    await _sweep()

    assert await _exists(M.TranscriptSegment, recent)


# --------------------------------------------------------------------------- #
# the organization's own window
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_an_orgs_shorter_policy_is_the_one_applied(services_app_client,
                                                         storage):
    """`policy_for()` exists and is currently called by nothing.

    An organization that says "keep transcripts for 30 days" is entitled to
    that, and a global default of 365 does not override a customer's instruction
    about their own employees' conversations.
    """
    meeting_id = await _room(org_retention={"transcript_days": 30})
    sixty = await _caption(meeting_id, age_days=60)

    await _sweep()

    assert not await _exists(M.TranscriptSegment, sixty), (
        "the organization's 30-day policy was ignored in favour of the "
        "deployment's 365-day default")


@pytest.mark.asyncio
async def test_a_meetings_policy_beats_its_orgs(services_app_client, storage):
    """One room, one decision. A class's drop should not inherit the company's
    archive window."""
    meeting_id = await _room(org_retention={"transcript_days": 365},
                             meeting_retention={"transcript_days": 7})
    ten = await _caption(meeting_id, age_days=10)

    await _sweep()

    assert not await _exists(M.TranscriptSegment, ten)


# --------------------------------------------------------------------------- #
# the recorded audio
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_the_recording_goes_when_its_retention_ends_and_the_caption_stays(
        services_app_client, storage):
    """Audio and text have different windows, and both are being missed.

    The pipeline stores a WAV against the caption row; the sweep only ever
    looked at `AudioSession.audio_object_key`, which no code writes. A listener
    who deleted nothing else should still not be able to hear last month.
    Seven days of audio, ninety days of text here, so the row has to remain.
    """
    meeting_id = await _room(org_retention={"audio_days": 7,
                                            "transcript_days": 90})
    key = f"audio/{uuid.uuid4()}/segment.wav"
    row = await _caption(meeting_id, age_days=30, audio_key=key)

    await _sweep()

    assert key in storage.deleted, (
        f"the sweep never asked to delete the stored recording {key}")
    assert await _audio_key(row) is None, (
        "the object is gone but the row still points at it")
    assert await _exists(M.TranscriptSegment, row), (
        "audio retention deleted a caption that is still inside its own window")


@pytest.mark.asyncio
async def test_a_recording_still_inside_its_window_is_left_alone(
        services_app_client, storage):
    meeting_id = await _room(org_retention={"audio_days": 30})
    key = f"audio/{uuid.uuid4()}/fresh.wav"
    await _caption(meeting_id, age_days=5, audio_key=key)

    await _sweep()

    assert storage.deleted == []


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_the_sweep_says_how_much_it_removed(services_app_client, storage):
    """The counts are the only evidence an operator gets that a policy ran.

    A `counts` dict without a transcripts key is how a retention job can run
    hourly for a year and delete nothing, exactly as it did here.
    """
    meeting_id = await _room()
    await _caption(meeting_id, age_days=400)

    counts = await _sweep()

    assert "transcripts" in counts, counts
    assert counts["transcripts"] >= 1, (
        "the sweep reported nothing removed while a row was removed")
    assert "audio_objects" in counts and counts["audio_objects"] >= 0


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

async def _sweep() -> dict:
    async with db_session() as db:
        return await R.sweep(db)


async def _translation_id(segment_id: uuid.UUID) -> uuid.UUID:
    async with db_session() as db:
        row = (await db.execute(select(M.TranslationSegment).where(
            M.TranslationSegment.segment_id == segment_id))).scalars().first()
        assert row is not None, "the fixture did not create a translation"
        return row.id
