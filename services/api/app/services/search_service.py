"""Tenant-scoped search across TalkFlow meeting and translation data.

The PostgreSQL backend uses native full-text search; SQLite uses a portable LIKE
fallback. Keep the response keys stable: callers and SearchResponse depend on them.
"""
from __future__ import annotations

import logging
import re
import unicodedata
import uuid
from typing import Any, Protocol

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as M

log = logging.getLogger("app.search")

# Defensive bounds avoid pathological queries and Postgres tsquery syntax errors.
MAX_QUERY_LENGTH = 200
MAX_QUERY_TERMS = 8
DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def normalize_query(query: str) -> str:
    """Trim and collapse whitespace without changing the user's search spelling."""
    return " ".join((query or "").split())[:MAX_QUERY_LENGTH]


def query_terms(query: str) -> list[str]:
    """Return safe lexical terms for PostgreSQL prefix full-text search.

    Terms are escaped by allowing Unicode letters/numbers and underscore only.
    This prevents operator syntax in user input from being interpreted as tsquery.
    """
    # Python's standard re \w excludes all Unicode combining marks. Build
    # tokens by Unicode general category so Indic and other combining-mark
    # scripts remain intact without adding a runtime regex dependency.
    tokens: list[str] = []
    current: list[str] = []
    for char in query:
        category = unicodedata.category(char)
        if category[0] in {"L", "N"}:
            current.append(char)
        elif category[0] == "M" and current:
            current.append(char)
        elif char == "_" and current:
            current.append(char)
        else:
            if current:
                tokens.append("".join(current))
                current = []
    if current:
        tokens.append("".join(current))
    return tokens[:MAX_QUERY_TERMS]


def build_tsquery(query: str) -> str:
    """Build a conjunction of safely quoted prefix terms.

    Quoting each normalized token ensures punctuation supplied by a user is
    never interpreted as a tsquery operator. Apostrophes are normalized to
    token boundaries before quoting.
    """
    # query_terms emits only Unicode letters, numbers, combining marks, and
    # internal underscores. Do not run these through re \w: it strips marks
    # from scripts such as Devanagari and would change the query semantics.
    terms = query_terms(query)
    return " & ".join(f"'{term}':*" for term in terms if term.strip("_"))


class SearchBackend(Protocol):
    async def search(
        self, db: AsyncSession, org_id: uuid.UUID, query: str, limit: int
    ) -> dict[str, list[dict]]: ...


def _empty_result() -> dict[str, list[dict]]:
    return {"meetings": [], "segments": [], "documents": [], "chat_messages": []}


def _segment_result(seg: M.TranscriptSegment, meeting: M.Meeting) -> dict:
    return {
        "id": str(seg.id),
        "meeting_id": str(seg.meeting_id),
        "meeting_title": meeting.title,
        "seq": seg.seq,
        "speaker": seg.speaker_name,
        "lang": seg.source_lang,
        "text": seg.source_text[:300],
        "created_at": seg.created_at.isoformat(),
    }


def _message_result(msg: M.ChatMessage, meeting: M.Meeting) -> dict:
    return {
        "id": str(msg.id),
        "meeting_id": str(msg.meeting_id),
        "meeting_title": meeting.title,
        "sender": msg.sender_name,
        "lang": msg.detected_lang,
        "text": msg.original_text[:300],
        "created_at": msg.created_at.isoformat(),
    }


class PostgresSearch:
    """PostgreSQL prefix full-text search with stable, tenant-scoped results."""

    async def search(
        self, db: AsyncSession, org_id: uuid.UUID, query: str, limit: int
    ) -> dict[str, list[dict]]:
        out = _empty_result()
        tsq = build_tsquery(query)
        # Empty/punctuation-only queries are not match-all queries.
        if not tsq:
            return out

        # Final transcript segments are canonical human speech. Search derivatives
        # separately rather than replacing the immutable source text with a translation.
        res = await db.execute(
            select(M.TranscriptSegment, M.Meeting)
            .join(M.Meeting, M.Meeting.id == M.TranscriptSegment.meeting_id)
            .where(
                M.Meeting.org_id == org_id,
                M.TranscriptSegment.is_final.is_(True),
                func.to_tsvector("simple", M.TranscriptSegment.source_text)
                .op("@@")(func.to_tsquery("simple", tsq)),
            )
            .order_by(M.TranscriptSegment.created_at.desc())
            .limit(limit)
        )
        out["segments"] = [_segment_result(seg, meeting) for seg, meeting in res.all()]

        # Also search finalized translation derivatives attached to meetings.
        res = await db.execute(
            select(M.TranslationSegment, M.TranscriptSegment, M.Meeting)
            .join(M.TranscriptSegment, M.TranscriptSegment.id == M.TranslationSegment.segment_id)
            .join(M.Meeting, M.Meeting.id == M.TranscriptSegment.meeting_id)
            .where(
                M.Meeting.org_id == org_id,
                M.TranscriptSegment.is_final.is_(True),
                M.TranslationSegment.target_text != "",
                func.to_tsvector("simple", M.TranslationSegment.target_text)
                .op("@@")(func.to_tsquery("simple", tsq)),
            )
            .order_by(M.TranslationSegment.created_at.desc())
            .limit(limit)
        )
        for translation, seg, meeting in res.all():
            out["segments"].append({
                **_segment_result(seg, meeting),
                "matched_field": "translation",
                "matched_text": translation.target_text[:300],
                "target_lang": translation.target_lang,
            })

        res = await db.execute(
            select(M.Document)
            .where(M.Document.org_id == org_id, M.Document.filename.ilike(f"%{query}%"))
            .order_by(M.Document.created_at.desc()).limit(limit)
        )
        out["documents"] = [{
            "id": str(d.id), "filename": d.filename, "status": d.status,
            "target_lang": d.target_lang, "created_at": d.created_at.isoformat()
        } for d in res.scalars().all()]

        res = await db.execute(
            select(M.ChatMessage, M.Meeting)
            .join(M.Meeting, M.Meeting.id == M.ChatMessage.meeting_id)
            .where(
                M.Meeting.org_id == org_id,
                func.to_tsvector("simple", M.ChatMessage.original_text)
                .op("@@")(func.to_tsquery("simple", tsq)),
            )
            .order_by(M.ChatMessage.created_at.desc()).limit(limit)
        )
        out["chat_messages"] = [_message_result(msg, meeting) for msg, meeting in res.all()]

        res = await db.execute(
            select(M.Meeting)
            .where(M.Meeting.org_id == org_id, M.Meeting.title.ilike(f"%{query}%"))
            .order_by(M.Meeting.created_at.desc()).limit(limit)
        )
        out["meetings"] = [{
            "id": str(m.id), "title": m.title, "status": m.status,
            "created_at": m.created_at.isoformat()
        } for m in res.scalars().all()]
        return out


class LikeSearch:
    """SQLite/dev fallback with the same response contract and tenant scope."""

    async def search(
        self, db: AsyncSession, org_id: uuid.UUID, query: str, limit: int
    ) -> dict[str, list[dict]]:
        out = _empty_result()
        like = f"%{query}%"
        if not query:
            return out

        res = await db.execute(
            select(M.TranscriptSegment, M.Meeting)
            .join(M.Meeting, M.Meeting.id == M.TranscriptSegment.meeting_id)
            .where(
                M.Meeting.org_id == org_id,
                M.TranscriptSegment.is_final.is_(True),
                M.TranscriptSegment.source_text.ilike(like),
            )
            .order_by(M.TranscriptSegment.created_at.desc()).limit(limit)
        )
        out["segments"] = [_segment_result(seg, meeting) for seg, meeting in res.all()]

        res = await db.execute(
            select(M.TranslationSegment, M.TranscriptSegment, M.Meeting)
            .join(M.TranscriptSegment, M.TranscriptSegment.id == M.TranslationSegment.segment_id)
            .join(M.Meeting, M.Meeting.id == M.TranscriptSegment.meeting_id)
            .where(
                M.Meeting.org_id == org_id,
                M.TranscriptSegment.is_final.is_(True),
                M.TranslationSegment.target_text.ilike(like),
            )
            .order_by(M.TranslationSegment.created_at.desc()).limit(limit)
        )
        for translation, seg, meeting in res.all():
            out["segments"].append({
                **_segment_result(seg, meeting),
                "matched_field": "translation",
                "matched_text": translation.target_text[:300],
                "target_lang": translation.target_lang,
            })

        res = await db.execute(
            select(M.Document).where(M.Document.org_id == org_id, M.Document.filename.ilike(like))
            .order_by(M.Document.created_at.desc()).limit(limit)
        )
        out["documents"] = [{
            "id": str(d.id), "filename": d.filename, "status": d.status,
            "target_lang": d.target_lang, "created_at": d.created_at.isoformat()
        } for d in res.scalars().all()]

        res = await db.execute(
            select(M.ChatMessage, M.Meeting)
            .join(M.Meeting, M.Meeting.id == M.ChatMessage.meeting_id)
            .where(M.Meeting.org_id == org_id, M.ChatMessage.original_text.ilike(like))
            .order_by(M.ChatMessage.created_at.desc()).limit(limit)
        )
        out["chat_messages"] = [_message_result(msg, meeting) for msg, meeting in res.all()]

        res = await db.execute(
            select(M.Meeting).where(M.Meeting.org_id == org_id, M.Meeting.title.ilike(like))
            .order_by(M.Meeting.created_at.desc()).limit(limit)
        )
        out["meetings"] = [{
            "id": str(m.id), "title": m.title, "status": m.status,
            "created_at": m.created_at.isoformat()
        } for m in res.scalars().all()]
        return out


_backend: SearchBackend | None = None


def get_backend() -> SearchBackend:
    global _backend
    if _backend is None:
        # Choose for the actual bound engine (configuration can fall back to SQLite).
        from app.db.session import engine
        _backend = PostgresSearch() if engine().dialect.name == "postgresql" else LikeSearch()
    return _backend


async def search_all(
    db: AsyncSession,
    org_id: uuid.UUID,
    query: str,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    query = normalize_query(query)
    if not query:
        return {"meetings": [], "segments": [], "documents": [], "chat_messages": [],
                "glossary_terms": [], "tm_entries": []}
    limit = max(1, min(int(limit), MAX_LIMIT))
    result = await get_backend().search(db, org_id, query, limit)

    # Small glossary/TM tables use LIKE for portability, always scoped through org.
    like = f"%{query}%"
    res = await db.execute(
        select(M.GlossaryTerm, M.Glossary)
        .join(M.Glossary, M.Glossary.id == M.GlossaryTerm.glossary_id)
        .where(
            M.Glossary.org_id == org_id,
            or_(M.GlossaryTerm.source_text.ilike(like), M.GlossaryTerm.target_text.ilike(like)),
        )
        .limit(limit)
    )
    result["glossary_terms"] = [
        {"id": str(t.id), "glossary": g.name, "source": t.source_text, "target": t.target_text}
        for t, g in res.all()
    ]
    res = await db.execute(
        select(M.TranslationMemoryEntry, M.TranslationMemory)
        .join(M.TranslationMemory, M.TranslationMemory.id == M.TranslationMemoryEntry.tm_id)
        .where(
            M.TranslationMemory.org_id == org_id,
            or_(M.TranslationMemoryEntry.source_text.ilike(like),
                M.TranslationMemoryEntry.target_text.ilike(like)),
        )
        .limit(limit)
    )
    result["tm_entries"] = [
        {"id": str(e.id), "tm": tm.name, "source": e.source_text[:200],
         "target": e.target_text[:200]} for e, tm in res.all()
    ]
    return result
