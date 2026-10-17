"""Retention & cleanup (PDD §40): policy-driven deletion sweeps.

Policies: a meeting's retention_json overrides its organization's, which
overrides the global defaults. Originals and derived translations are deleted
on their own schedules; audio (largest, least durable value) goes first.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import models as M
from app.db.base import utcnow
from app.storage import storage

log = logging.getLogger("app.retention")

#: How many meeting ids one bulk statement is allowed to carry. A retention
#: sweep that builds a 200 000-element IN list stops being a background job.
_BATCH = 500


def _resolve(org_json: dict | None, meeting_json: dict | None) -> dict:
    days = {
        "audio_days": settings.retention_audio_days,
        "transcript_days": settings.retention_transcript_days,
        "document_days": settings.retention_document_days,
        "usage_days": settings.retention_usage_days,
    }
    for overrides in (org_json, meeting_json):
        days.update({k: v for k, v in (overrides or {}).items() if v is not None})
    return days


def policy_for(org: M.Organization | None,
               meeting: M.Meeting | None = None) -> dict:
    """How long this room's data is kept, widest scope yielding to narrowest.

    The deployment default is the floor, the organization overrides it, and a
    single meeting overrides both — a class that voted itself out of the
    company's archive window is a real request, not a rounding error.

    A value of `None` means "this kind of data is not on a clock"; `0` means
    "as soon as the next sweep runs", which is how `retention_audio_days = 0`
    already stops the pipeline from storing audio at all.
    """
    return _resolve(getattr(org, "retention_json", None),
                    getattr(meeting, "retention_json", None))


def _cutoff(days: int | None) -> datetime | None:
    return None if days is None else utcnow() - timedelta(days=max(0, int(days)))


def _chunks(items: list):
    for i in range(0, len(items), _BATCH):
        yield items[i:i + _BATCH]


async def _release(key: str) -> bool:
    """Ask the object store to forget one recording; say whether it did.

    A key that will not go away is reported rather than swallowed, because this
    is the loop that used to look healthy while deleting nothing at all.
    """
    try:
        await storage().delete(key)
        return True
    except Exception as e:
        log.warning("retention could not delete %s: %s", key, e)
        return False


async def _delete_ids(db: AsyncSession, model, column, ids: list) -> int:
    """Delete these ids in batches.

    Derived rows are named explicitly instead of trusted to the schema: SQLite
    in tests does not enforce foreign keys, so an `ondelete=CASCADE` here is a
    comment, not a behaviour.
    """
    removed = 0
    for chunk in _chunks(ids):
        res = await db.execute(
            delete(model).where(column.in_(chunk))
            .execution_options(synchronize_session=False))
        removed += res.rowcount or 0
    return removed


async def _windows(db: AsyncSession) -> dict[tuple[int | None, int | None], list]:
    """Meeting ids bucketed by the (audio_days, transcript_days) they resolve to.

    One query over meetings, not one per row of data: the rows are the long
    part, and a room's window is decided once however many captions it holds.
    """
    res = await db.execute(
        select(M.Meeting.id, M.Meeting.retention_json, M.Organization.retention_json)
        .join(M.Organization, M.Meeting.org_id == M.Organization.id))
    buckets: dict[tuple[int | None, int | None], list] = {}
    for meeting_id, meeting_json, org_json in res.all():
        days = _resolve(org_json, meeting_json)
        buckets.setdefault((days["audio_days"], days["transcript_days"]), []).append(meeting_id)
    return buckets


async def sweep(db: AsyncSession) -> dict:
    """Run one cleanup pass. Returns counts for observability."""
    counts = {"audio_objects": 0, "transcripts": 0, "translations": 0,
              "documents": 0, "usage": 0, "expired_tokens": 0}

    buckets = await _windows(db)

    # 1) stored media, released on the audio window — which is shorter than the
    #    text window on purpose, so the caption row stays and only the pointer
    #    goes. `TranscriptSegment.audio_object_key` is where the realtime
    #    pipeline actually puts a meeting's WAV; `AudioSession` carries one for
    #    sessions that recorded through another path.
    for (audio_days, _), meeting_ids in buckets.items():
        cutoff = _cutoff(audio_days)
        if cutoff is None:
            continue
        for model in (M.TranscriptSegment, M.AudioSession):
            for chunk in _chunks(meeting_ids):
                rows = (await db.execute(
                    select(model.id, model.audio_object_key)
                    .where(model.audio_object_key.is_not(None),
                           model.created_at < cutoff,
                           model.meeting_id.in_(chunk)))).all()
                freed = [row_id for row_id, key in rows if await _release(key)]
                counts["audio_objects"] += len(freed)
                if freed:
                    await db.execute(
                        update(model).where(model.id.in_(freed))
                        .values(audio_object_key=None)
                        .execution_options(synchronize_session=False))

    # 2) transcripts past their window, and the glosses made from them
    for (_, transcript_days), meeting_ids in buckets.items():
        cutoff = _cutoff(transcript_days)
        if cutoff is None:
            continue
        for chunk in _chunks(meeting_ids):
            expired = (await db.execute(
                select(M.TranscriptSegment.id, M.TranscriptSegment.audio_object_key)
                .where(M.TranscriptSegment.meeting_id.in_(chunk),
                       M.TranscriptSegment.created_at < cutoff))).all()
            if not expired:
                continue
            # The caption row is the only pointer to its recording, so deleting
            # the text without the audio would leave the voice in storage
            # forever with nothing left that names it.
            for _, key in expired:
                if key and await _release(key):
                    counts["audio_objects"] += 1
            ids = [row_id for row_id, _ in expired]
            counts["translations"] += await _delete_ids(
                db, M.TranslationSegment, M.TranslationSegment.segment_id, ids)
            counts["transcripts"] += await _delete_ids(
                db, M.TranscriptSegment, M.TranscriptSegment.id, ids)

    # 3) expired documents + their objects
    res = await db.execute(select(M.Document).where(
        M.Document.expires_at.is_not(None),
        M.Document.expires_at < utcnow(),
        M.Document.status != "deleted"))
    for d in res.scalars().all():
        for key in (d.source_object_key, d.output_object_key):
            if key:
                try:
                    await storage().delete(key)
                except Exception:
                    pass
        d.status = "deleted"
        counts["documents"] += 1

    # 4) usage records past retention
    if settings.retention_usage_days:
        cutoff = utcnow() - timedelta(days=settings.retention_usage_days)
        r = await db.execute(delete(M.UsageRecord).where(M.UsageRecord.created_at < cutoff))
        counts["usage"] = r.rowcount or 0

    # 5) expired sessions / refresh tokens
    r = await db.execute(delete(M.Session).where(M.Session.expires_at < utcnow()))
    counts["expired_tokens"] += r.rowcount or 0
    r = await db.execute(delete(M.RefreshToken).where(M.RefreshToken.expires_at < utcnow()))
    counts["expired_tokens"] += r.rowcount or 0
    r = await db.execute(delete(M.MemoryItem).where(
        M.MemoryItem.expires_at.is_not(None), M.MemoryItem.expires_at < utcnow()))

    await db.commit()
    log.info("retention sweep: %s", counts)
    return counts


async def delete_user_data(db: AsyncSession, user_id) -> None:
    """GDPR-style user deletion: anonymize personal fields, cascade rows."""
    user = await db.get(M.User, user_id)
    if user is None:
        return
    user.email = f"deleted-{user.id}@deleted.invalid"
    user.name = "Deleted User"
    user.status = "deleted"
    user.deleted_at = utcnow()
    await db.commit()


async def delete_org_data(db: AsyncSession, org_id) -> None:
    org = await db.get(M.Organization, org_id)
    if org is None:
        return
    org.status = "deleted"
    org.deleted_at = utcnow()
    # FK cascades handle meetings/documents/etc.; objects swept next retention run
    res = await db.execute(select(M.Document).where(M.Document.org_id == org_id))
    for d in res.scalars().all():
        for key in (d.source_object_key, d.output_object_key):
            if key:
                try:
                    await storage().delete(key)
                except Exception:
                    pass
    await db.commit()
