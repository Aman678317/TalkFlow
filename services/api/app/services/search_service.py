"""Search service — PostgreSQL FTS first, LIKE fallback for SQLite (PDD §47).

Adapter design: `SearchBackend` protocol keeps Elasticsearch/OpenSearch a
drop-in later without touching callers.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Protocol

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as M

log = logging.getLogger("app.search")


class SearchBackend(Protocol):
    async def search(self, db: AsyncSession, org_id: uuid.UUID, query: str,
                     limit: int) -> dict[str, list[dict]]: ...


class PostgresSearch:
    """to_tsvector/tsquery full-text search across transcripts, chat, docs."""

    async def search(self, db: AsyncSession, org_id: uuid.UUID, query: str,
                     limit: int) -> dict[str, list[dict]]:
        tsq = " & ".join(f"{w}:*" for w in query.split()[:8])
        out: dict[str, list[dict]] = {"meetings": [], "segments": [],
                                      "documents": [], "chat_messages": []}
        # segments (via meetings for tenant scope)
        res = await db.execute(
            select(M.TranscriptSegment, M.Meeting)
            .join(M.Meeting, M.Meeting.id == M.TranscriptSegment.meeting_id)
            .where(M.Meeting.org_id == org_id,
                   func.to_tsvector("simple", M.TranscriptSegment.source_text)
                   .op("@@")(func.to_tsquery("simple", tsq)))
            .order_by(M.TranscriptSegment.created_at.desc()).limit(limit))
        for seg, meeting in res.all():
            out["segments"].append({
                "id": str(seg.id), "meeting_id": str(seg.meeting_id),
                "meeting_title": meeting.title, "seq": seg.seq,
                "speaker": seg.speaker_name, "lang": seg.source_lang,
                "text": seg.source_text[:300],
                "created_at": seg.created_at.isoformat()})
        # documents by filename
        res = await db.execute(
            select(M.Document).where(
                M.Document.org_id == org_id,
                M.Document.filename.ilike(f"%{query}%"))
            .order_by(M.Document.created_at.desc()).limit(limit))
        for d in res.scalars().all():
            out["documents"].append({
                "id": str(d.id), "filename": d.filename, "status": d.status,
                "target_lang": d.target_lang,
                "created_at": d.created_at.isoformat()})
        # chat messages
        res = await db.execute(
            select(M.ChatMessage, M.Meeting)
            .join(M.Meeting, M.Meeting.id == M.ChatMessage.meeting_id)
            .where(M.Meeting.org_id == org_id,
                   func.to_tsvector("simple", M.ChatMessage.original_text)
                   .op("@@")(func.to_tsquery("simple", tsq)))
            .order_by(M.ChatMessage.created_at.desc()).limit(limit))
        for msg, meeting in res.all():
            out["chat_messages"].append({
                "id": str(msg.id), "meeting_id": str(msg.meeting_id),
                "meeting_title": meeting.title, "sender": msg.sender_name,
                "lang": msg.detected_lang, "text": msg.original_text[:300],
                "created_at": msg.created_at.isoformat()})
        # meetings by title
        res = await db.execute(
            select(M.Meeting).where(
                M.Meeting.org_id == org_id, M.Meeting.title.ilike(f"%{query}%"))
            .order_by(M.Meeting.created_at.desc()).limit(limit))
        for m in res.scalars().all():
            out["meetings"].append({
                "id": str(m.id), "title": m.title, "status": m.status,
                "created_at": m.created_at.isoformat()})
        return out


class LikeSearch:
    """SQLite/dev fallback — same output contract."""

    async def search(self, db: AsyncSession, org_id: uuid.UUID, query: str,
                     limit: int) -> dict[str, list[dict]]:
        like = f"%{query}%"
        out: dict[str, list[dict]] = {"meetings": [], "segments": [],
                                      "documents": [], "chat_messages": []}
        res = await db.execute(
            select(M.TranscriptSegment, M.Meeting)
            .join(M.Meeting, M.Meeting.id == M.TranscriptSegment.meeting_id)
            .where(M.Meeting.org_id == org_id,
                   M.TranscriptSegment.source_text.ilike(like))
            .order_by(M.TranscriptSegment.created_at.desc()).limit(limit))
        for seg, meeting in res.all():
            out["segments"].append({
                "id": str(seg.id), "meeting_id": str(seg.meeting_id),
                "meeting_title": meeting.title, "seq": seg.seq,
                "speaker": seg.speaker_name, "lang": seg.source_lang,
                "text": seg.source_text[:300],
                "created_at": seg.created_at.isoformat()})
        res = await db.execute(
            select(M.Document).where(M.Document.org_id == org_id,
                                     M.Document.filename.ilike(like))
            .order_by(M.Document.created_at.desc()).limit(limit))
        for d in res.scalars().all():
            out["documents"].append({
                "id": str(d.id), "filename": d.filename, "status": d.status,
                "target_lang": d.target_lang,
                "created_at": d.created_at.isoformat()})
        res = await db.execute(
            select(M.ChatMessage, M.Meeting)
            .join(M.Meeting, M.Meeting.id == M.ChatMessage.meeting_id)
            .where(M.Meeting.org_id == org_id,
                   M.ChatMessage.original_text.ilike(like))
            .order_by(M.ChatMessage.created_at.desc()).limit(limit))
        for msg, meeting in res.all():
            out["chat_messages"].append({
                "id": str(msg.id), "meeting_id": str(msg.meeting_id),
                "meeting_title": meeting.title, "sender": msg.sender_name,
                "lang": msg.detected_lang, "text": msg.original_text[:300],
                "created_at": msg.created_at.isoformat()})
        res = await db.execute(
            select(M.Meeting).where(M.Meeting.org_id == org_id,
                                    M.Meeting.title.ilike(like))
            .order_by(M.Meeting.created_at.desc()).limit(limit))
        for m in res.scalars().all():
            out["meetings"].append({
                "id": str(m.id), "title": m.title, "status": m.status,
                "created_at": m.created_at.isoformat()})
        return out


_backend: SearchBackend | None = None


def get_backend() -> SearchBackend:
    global _backend
    if _backend is None:
        # dialect of the ACTUAL bound engine (config may have fallen back
        # from postgres to sqlite at startup)
        from app.db.session import engine
        dialect = engine().dialect.name
        _backend = PostgresSearch() if dialect == "postgresql" else LikeSearch()
    return _backend


async def search_all(db: AsyncSession, org_id: uuid.UUID, query: str,
                     limit: int = 20) -> dict[str, Any]:
    result = await get_backend().search(db, org_id, query, limit)
    # glossary terms + TM entries (small tables, LIKE is fine everywhere)
    like = f"%{query}%"
    res = await db.execute(
        select(M.GlossaryTerm, M.Glossary)
        .join(M.Glossary, M.Glossary.id == M.GlossaryTerm.glossary_id)
        .where(M.Glossary.org_id == org_id,
               or_(M.GlossaryTerm.source_text.ilike(like),
                   M.GlossaryTerm.target_text.ilike(like)))
        .limit(limit))
    result["glossary_terms"] = [
        {"id": str(t.id), "glossary": g.name, "source": t.source_text,
         "target": t.target_text} for t, g in res.all()]
    res = await db.execute(
        select(M.TranslationMemoryEntry, M.TranslationMemory)
        .join(M.TranslationMemory, M.TranslationMemory.id == M.TranslationMemoryEntry.tm_id)
        .where(M.TranslationMemory.org_id == org_id,
               M.TranslationMemoryEntry.source_text.ilike(like))
        .limit(limit))
    result["tm_entries"] = [
        {"id": str(e.id), "tm": tm.name, "source": e.source_text[:200],
         "target": e.target_text[:200]} for e, tm in res.all()]
    return result
