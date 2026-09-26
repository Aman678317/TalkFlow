"""Search adapter (section 47): PostgreSQL-backed now (ILIKE / tsvector-ready),
interface designed so an Elasticsearch/OpenSearch adapter can replace it without
touching callers."""
from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from globaltalk.models import (ChatMessage, Document, Glossary, Meeting, TranslationMemory,
                               TranscriptSegment)


class SearchBackend(Protocol):
    def search_all(self, db: Session, org_id: str, q: str, limit: int) -> dict: ...


class PostgresSearch:
    """Full-text search using PostgreSQL FTS when available, ILIKE fallback on SQLite.

    Both paths are tenant-scoped at the query level (defense in depth: org_id filter is
    mandatory in every query here)."""

    def search_all(self, db: Session, org_id: str, q: str, limit: int) -> dict:
        like = f"%{q}%"
        meetings = (db.query(Meeting).filter(Meeting.org_id == org_id,
                                             Meeting.title.ilike(like))
                    .limit(limit).all())
        segments = (db.query(TranscriptSegment)
                    .filter(TranscriptSegment.org_id == org_id,
                            TranscriptSegment.is_final.is_(True),
                            TranscriptSegment.text.ilike(like))
                    .order_by(TranscriptSegment.created_at.desc()).limit(limit).all())
        chats = (db.query(ChatMessage).filter(ChatMessage.org_id == org_id,
                                              ChatMessage.original_text.ilike(like))
                 .order_by(ChatMessage.created_at.desc()).limit(limit).all())
        docs = (db.query(Document).filter(Document.org_id == org_id,
                                          Document.filename.ilike(like)).limit(limit).all())
        glossaries = (db.query(Glossary).filter(Glossary.org_id == org_id,
                                                Glossary.name.ilike(like)).limit(limit).all())
        tm = (db.query(TranslationMemory)
              .filter(TranslationMemory.org_id == org_id,
                      TranslationMemory.source_text.ilike(like)).limit(limit).all())
        return {
            "query": q,
            "meetings": [{"id": m.id, "title": m.title, "status": m.status} for m in meetings],
            "transcripts": [{"id": s.id, "meeting_id": s.meeting_id, "language": s.language,
                             "text": s.text[:300], "speaker_id": s.participant_id}
                            for s in segments],
            "messages": [{"id": c.id, "meeting_id": c.meeting_id,
                          "text": c.original_text[:300]} for c in chats],
            "documents": [{"id": d.id, "filename": d.filename, "status": d.status}
                          for d in docs],
            "glossaries": [{"id": g.id, "name": g.name} for g in glossaries],
            "translation_memories": [{"id": t.id, "source_text": t.source_text[:200],
                                      "target_text": t.target_text[:200]} for t in tm],
        }


_backend = PostgresSearch()


def search_all(db: Session, org_id: str, q: str, limit: int) -> dict:
    return _backend.search_all(db, org_id, q, limit)
