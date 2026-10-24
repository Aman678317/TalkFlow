"""FastAPI Router for DeepL-style Saved Translations, Notes, and Multilingual Annotations."""
from __future__ import annotations

import re
import time
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as M
from app.db.session import get_db
from app.deps import Principal, bearer, get_principal

router = APIRouter(prefix="/notes", tags=["Notes & Annotations"])


async def optional_principal(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> Principal | None:
    try:
        return await get_principal(request, creds, db)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #

class AnnotationSpan(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    text: str
    start: int
    end: int
    tag: str = "vocabulary"  # vocabulary, idiom, grammar, review, style, context
    comment: str = ""
    color: str = "blue"  # blue, amber, emerald, purple, rose


class NoteCreateRequest(BaseModel):
    source_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    title: str | None = None
    note: str | None = ""
    tags: list[str] | None = None
    annotations: list[AnnotationSpan] | None = None
    is_favorite: bool = True
    translation_id: str | None = None


class NoteUpdateRequest(BaseModel):
    title: str | None = None
    note: str | None = None
    tags: list[str] | None = None
    annotations: list[AnnotationSpan] | None = None
    is_favorite: bool | None = None


class NoteOut(BaseModel):
    id: str
    org_id: str | None = None
    user_id: str | None = None
    translation_id: str | None = None
    title: str
    source_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    note: str
    tags: list[str]
    annotations: list[dict[str, Any]]
    is_favorite: bool
    created_at: datetime
    updated_at: datetime
    highlight_source: str | None = None
    highlight_target: str | None = None
    highlight_note: str | None = None


class NoteSearchResponse(BaseModel):
    items: list[NoteOut]
    total: int
    query: str | None = None
    latency_ms: float
    available_tags: list[str]
    languages_represented: list[str]


# --------------------------------------------------------------------------- #
# Helpers: Multi-Script Normalization & Highlighting
# --------------------------------------------------------------------------- #

def _normalize_search(s: str) -> str:
    """NFC normalization and lowercase for universal cross-script search."""
    if not s:
        return ""
    # NFC preserves Devanagari, Arabic, CJK, and Cyrillic composition cleanly
    return unicodedata.normalize("NFC", s).strip().lower()


def _highlight_text(text: str, query: str) -> str:
    """Surrounds occurrences of query terms with <mark> tags, preserving casing."""
    if not text or not query:
        return text
    q_terms = [re.escape(t) for t in query.split() if len(t) > 0]
    if not q_terms:
        return text
    pattern = re.compile(f"({'|'.join(q_terms)})", re.IGNORECASE)
    return pattern.sub(r"<mark>\1</mark>", text)


def _row_to_out(n: M.TranslationNote, q: str | None = None) -> NoteOut:
    h_src = _highlight_text(n.source_text, q) if q else None
    h_tgt = _highlight_text(n.translated_text, q) if q else None
    h_note = _highlight_text(n.note, q) if q and n.note else None
    return NoteOut(
        id=str(n.id),
        org_id=str(n.org_id) if n.org_id else None,
        user_id=str(n.user_id) if n.user_id else None,
        translation_id=str(n.translation_id) if n.translation_id else None,
        title=n.title or (n.source_text[:40] + ("…" if len(n.source_text) > 40 else "")),
        source_text=n.source_text,
        translated_text=n.translated_text,
        source_lang=n.source_lang,
        target_lang=n.target_lang,
        note=n.note,
        tags=list(n.tags_json or []),
        annotations=list(n.annotations_json or []),
        is_favorite=n.is_favorite,
        created_at=n.created_at,
        updated_at=n.updated_at,
        highlight_source=h_src,
        highlight_target=h_tgt,
        highlight_note=h_note,
    )


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@router.get("", response_model=NoteSearchResponse)
async def list_and_search_notes(
    q: str | None = Query(None, description="Search query across note, source, and translation"),
    source_lang: str | None = Query(None, description="Filter by source language code"),
    target_lang: str | None = Query(None, description="Filter by target language code"),
    tag: str | None = Query(None, description="Filter by tag name"),
    favorite: bool | None = Query(None, description="Filter favorites only"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    principal: Principal | None = Depends(optional_principal),
):
    """DeepL-style fast multilingual search across all saved translations and notes."""
    t0 = time.perf_counter()

    stmt = select(M.TranslationNote).order_by(desc(M.TranslationNote.created_at))

    if principal and principal.org_id:
        stmt = stmt.where(
            (M.TranslationNote.org_id == principal.org_id) | (M.TranslationNote.org_id.is_(None))
        )

    if source_lang:
        stmt = stmt.where(M.TranslationNote.source_lang == source_lang.strip().lower())
    if target_lang:
        stmt = stmt.where(M.TranslationNote.target_lang == target_lang.strip().lower())
    if favorite is not None:
        stmt = stmt.where(M.TranslationNote.is_favorite == favorite)

    result = await db.execute(stmt)
    all_rows = result.scalars().all()

    filtered = []
    norm_q = _normalize_search(q) if q else ""
    q_tokens = norm_q.split() if norm_q else []

    all_tags = set()
    langs_seen = set()

    for row in all_rows:
        row_tags = set(row.tags_json or [])
        all_tags.update(row_tags)
        langs_seen.add(row.source_lang)
        langs_seen.add(row.target_lang)

        if tag and tag not in row_tags:
            continue

        if not q_tokens:
            filtered.append(row)
            continue

        haystack = " ".join([
            row.title or "",
            row.note or "",
            row.source_text or "",
            row.translated_text or "",
            " ".join(row.tags_json or []),
            " ".join([a.get("text", "") + " " + a.get("comment", "") for a in (row.annotations_json or [])]),
        ])
        norm_haystack = _normalize_search(haystack)

        if all(token in norm_haystack for token in q_tokens):
            filtered.append(row)

    total = len(filtered)
    paged = filtered[offset : offset + limit]
    items = [_row_to_out(r, q=q) for r in paged]

    latency = round((time.perf_counter() - t0) * 1000, 2)
    return NoteSearchResponse(
        items=items,
        total=total,
        query=q,
        latency_ms=latency,
        available_tags=sorted(list(all_tags)),
        languages_represented=sorted(list(langs_seen)),
    )


@router.post("", response_model=NoteOut, status_code=201)
async def create_note(
    body: NoteCreateRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal | None = Depends(optional_principal),
):
    """Save a translation with notes, tags, and inline text annotations."""
    title = body.title.strip() if body.title else body.source_text.strip()[:60]
    raw_tid = None
    if body.translation_id:
        try:
            raw_tid = uuid.UUID(body.translation_id)
        except Exception:
            raw_tid = None

    note_obj = M.TranslationNote(
        id=uuid.uuid4(),
        org_id=principal.org_id if principal else None,
        user_id=principal.user_id if principal else None,
        translation_id=raw_tid,
        title=title,
        source_text=body.source_text.strip(),
        translated_text=body.translated_text.strip(),
        source_lang=body.source_lang.strip().lower(),
        target_lang=body.target_lang.strip().lower(),
        note=body.note.strip() if body.note else "",
        tags_json=body.tags or [],
        annotations_json=[a.model_dump() for a in (body.annotations or [])],
        is_favorite=body.is_favorite,
    )
    db.add(note_obj)
    await db.commit()
    await db.refresh(note_obj)
    return _row_to_out(note_obj)


@router.get("/{note_id}", response_model=NoteOut)
async def get_note(
    note_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a single note by ID."""
    try:
        nid = uuid.UUID(note_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid note UUID format")
    note = await db.get(M.TranslationNote, nid)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return _row_to_out(note)


@router.patch("/{note_id}", response_model=NoteOut)
async def update_note(
    note_id: str,
    body: NoteUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update note content, tags, annotations, or favorite status."""
    try:
        nid = uuid.UUID(note_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid note UUID format")
    note = await db.get(M.TranslationNote, nid)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    if body.title is not None:
        note.title = body.title.strip()
    if body.note is not None:
        note.note = body.note.strip()
    if body.tags is not None:
        note.tags_json = body.tags
    if body.annotations is not None:
        note.annotations_json = [a.model_dump() for a in body.annotations]
    if body.is_favorite is not None:
        note.is_favorite = body.is_favorite

    note.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(note)
    return _row_to_out(note)


@router.delete("/{note_id}", status_code=204)
async def delete_note(
    note_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a note."""
    try:
        nid = uuid.UUID(note_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid note UUID format")
    note = await db.get(M.TranslationNote, nid)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    await db.delete(note)
    await db.commit()
    return Response(status_code=204)
