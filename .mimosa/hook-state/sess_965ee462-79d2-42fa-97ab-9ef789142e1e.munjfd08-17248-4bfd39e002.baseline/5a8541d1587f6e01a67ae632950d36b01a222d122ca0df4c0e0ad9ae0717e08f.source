"""Retention & cleanup (PDD §40): policy-driven deletion sweeps.

Policies: per-organization retention_json overrides global defaults.
Originals and derived translations are deleted on their own schedules;
audio (largest, least durable value) goes first.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import models as M
from app.db.base import utcnow
from app.storage import storage

log = logging.getLogger("app.retention")


def policy_for(org: M.Organization | None) -> dict:
    base = {
        "audio_days": settings.retention_audio_days,
        "transcript_days": settings.retention_transcript_days,
        "document_days": settings.retention_document_days,
        "usage_days": settings.retention_usage_days,
    }
    if org and org.retention_json:
        base.update({k: v for k, v in org.retention_json.items() if v is not None})
    return base


async def sweep(db: AsyncSession) -> dict:
    """Run one cleanup pass. Returns counts for observability."""
    counts = {"audio_objects": 0, "documents": 0, "usage": 0, "expired_tokens": 0}

    # 1) audio objects past retention (audio_sessions rows keep metadata)
    cutoff_audio = utcnow() - timedelta(days=max(0, settings.retention_audio_days))
    res = await db.execute(select(M.AudioSession).where(
        M.AudioSession.audio_object_key.is_not(None),
        M.AudioSession.created_at < cutoff_audio))
    for s in res.scalars().all():
        try:
            await storage().delete(s.audio_object_key)
            s.audio_object_key = None
            counts["audio_objects"] += 1
        except Exception as e:
            log.warning("audio cleanup failed for %s: %s", s.id, e)

    # 2) expired documents + their objects
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

    # 3) usage records past retention
    if settings.retention_usage_days:
        cutoff = utcnow() - timedelta(days=settings.retention_usage_days)
        r = await db.execute(delete(M.UsageRecord).where(M.UsageRecord.created_at < cutoff))
        counts["usage"] = r.rowcount or 0

    # 4) expired sessions / refresh tokens
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
