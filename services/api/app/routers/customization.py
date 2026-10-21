"""Customization hub routers: Glossaries, Translation Memory, Style Profiles
(PDD §16-§18). Versioned, tenant-scoped, import/export supported.
"""
from __future__ import annotations

import csv
import io
import logging
import uuid

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as M
from app.db.session import get_db
from app.deps import Principal, require_org_user
from app.errors import ConflictError, NotFoundError, ValidationError
from app.schemas import (
    GlossaryCreate, GlossaryOut, GlossaryTermIn, GlossaryTermOut, StyleProfileCreate,
    StyleProfileOut, TMCreate, TMEntryCreate, TMEntryDetail, TMEntryIn,
    TMEntryOut, TMEntryUpdate, TMOut,
)
from app.services import audit_service

log = logging.getLogger("app.routers.customization")

router = APIRouter(prefix="/api/v1", tags=["customization"])


# --------------------------------------------------------------------------- #
# Glossaries
# --------------------------------------------------------------------------- #

async def _get_glossary(db, glossary_id: uuid.UUID,
                        principal: Principal) -> M.Glossary:
    g = await db.get(M.Glossary, glossary_id)
    if g is None or g.org_id != principal.org_id:
        raise NotFoundError("Glossary not found.")
    return g


@router.post("/glossaries", response_model=GlossaryOut, status_code=201)
async def create_glossary(body: GlossaryCreate,
                          principal: Principal = Depends(require_org_user),
                          db: AsyncSession = Depends(get_db)):
    principal.require("manage_glossaries")
    g = M.Glossary(org_id=principal.org_id, name=body.name,
                   source_lang=body.source_lang, target_lang=body.target_lang,
                   description=body.description, created_by=principal.user_id)
    db.add(g)
    await db.flush()
    for t in body.terms:
        term = GlossaryTermIn.model_validate(t)
        db.add(M.GlossaryTerm(glossary_id=g.id, source_text=term.source_text,
                              target_text=term.target_text,
                              case_sensitive=term.case_sensitive,
                              spoken_variants_json=term.spoken_variants,
                              notes=term.notes))
    await audit_service.record(db, action="glossary.created", org_id=principal.org_id,
                               actor_id=principal.user_id, resource_type="glossary",
                               resource_id=str(g.id))
    await db.commit()
    await db.refresh(g)
    return GlossaryOut.model_validate(g)


@router.get("/glossaries", response_model=list[GlossaryOut])
async def list_glossaries(principal: Principal = Depends(require_org_user),
                          db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(M.Glossary).where(
        M.Glossary.org_id == principal.org_id).order_by(M.Glossary.created_at.desc()))
    return [GlossaryOut.model_validate(g) for g in res.scalars().all()]


@router.get("/glossaries/{glossary_id}", response_model=GlossaryOut)
async def get_glossary(glossary_id: uuid.UUID,
                       principal: Principal = Depends(require_org_user),
                       db: AsyncSession = Depends(get_db)):
    g = await _get_glossary(db, glossary_id, principal)
    return GlossaryOut.model_validate(g)


@router.post("/glossaries/{glossary_id}/terms", response_model=GlossaryTermOut,
             status_code=201)
async def add_term(glossary_id: uuid.UUID, body: GlossaryTermIn,
                   principal: Principal = Depends(require_org_user),
                   db: AsyncSession = Depends(get_db)):
    principal.require("manage_glossaries")
    g = await _get_glossary(db, glossary_id, principal)
    if g.status == "archived":
        raise ConflictError("Cannot modify an archived glossary; create a new version.")
    exists = (await db.execute(select(M.GlossaryTerm).where(
        M.GlossaryTerm.glossary_id == g.id,
        M.GlossaryTerm.source_text == body.source_text))).scalars().first()
    if exists:
        raise ConflictError("Term already exists in this glossary.")
    t = M.GlossaryTerm(glossary_id=g.id, source_text=body.source_text,
                       target_text=body.target_text,
                       case_sensitive=body.case_sensitive,
                       spoken_variants_json=body.spoken_variants, notes=body.notes)
    db.add(t)
    g.version += 1
    await db.commit()
    await db.refresh(t)
    return GlossaryTermOut.model_validate(t)


@router.put("/glossaries/{glossary_id}/terms/{term_id}",
            response_model=GlossaryTermOut)
async def update_term(glossary_id: uuid.UUID, term_id: uuid.UUID,
                      body: GlossaryTermIn,
                      principal: Principal = Depends(require_org_user),
                      db: AsyncSession = Depends(get_db)):
    principal.require("manage_glossaries")
    g = await _get_glossary(db, glossary_id, principal)
    t = await db.get(M.GlossaryTerm, term_id)
    if t is None or t.glossary_id != g.id:
        raise NotFoundError("Term not found.")
    t.source_text = body.source_text
    t.target_text = body.target_text
    t.case_sensitive = body.case_sensitive
    t.spoken_variants_json = body.spoken_variants
    t.notes = body.notes
    g.version += 1
    await db.commit()
    return GlossaryTermOut.model_validate(t)


@router.delete("/glossaries/{glossary_id}/terms/{term_id}", status_code=204)
async def delete_term(glossary_id: uuid.UUID, term_id: uuid.UUID,
                      principal: Principal = Depends(require_org_user),
                      db: AsyncSession = Depends(get_db)):
    principal.require("manage_glossaries")
    g = await _get_glossary(db, glossary_id, principal)
    t = await db.get(M.GlossaryTerm, term_id)
    if t is None or t.glossary_id != g.id:
        raise NotFoundError("Term not found.")
    await db.delete(t)
    g.version += 1
    await db.commit()


@router.post("/glossaries/{glossary_id}/activate", response_model=GlossaryOut)
async def activate_glossary(glossary_id: uuid.UUID,
                            principal: Principal = Depends(require_org_user),
                            db: AsyncSession = Depends(get_db)):
    principal.require("manage_glossaries")
    g = await _get_glossary(db, glossary_id, principal)
    g.status = "active"
    await audit_service.record(db, action="glossary.activated",
                               org_id=principal.org_id, actor_id=principal.user_id,
                               resource_type="glossary", resource_id=str(g.id),
                               details={"version": g.version})
    await db.commit()
    return GlossaryOut.model_validate(g)


@router.post("/glossaries/{glossary_id}/archive", response_model=GlossaryOut)
async def archive_glossary(glossary_id: uuid.UUID,
                           principal: Principal = Depends(require_org_user),
                           db: AsyncSession = Depends(get_db)):
    principal.require("manage_glossaries")
    g = await _get_glossary(db, glossary_id, principal)
    g.status = "archived"
    await db.commit()
    return GlossaryOut.model_validate(g)


@router.delete("/glossaries/{glossary_id}", status_code=204)
async def delete_glossary(glossary_id: uuid.UUID,
                          principal: Principal = Depends(require_org_user),
                          db: AsyncSession = Depends(get_db)):
    principal.require("manage_glossaries")
    g = await _get_glossary(db, glossary_id, principal)
    await db.delete(g)
    await audit_service.record(db, action="glossary.deleted", org_id=principal.org_id,
                               actor_id=principal.user_id, resource_type="glossary",
                               resource_id=str(glossary_id))
    await db.commit()


@router.post("/glossaries/{glossary_id}/import", response_model=dict)
async def import_glossary(glossary_id: uuid.UUID, file: UploadFile,
                          principal: Principal = Depends(require_org_user),
                          db: AsyncSession = Depends(get_db)):
    """CSV import: source_text,target_text[,spoken_variants(| separated)][,notes]"""
    principal.require("manage_glossaries")
    g = await _get_glossary(db, glossary_id, principal)
    data = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(data))
    added = skipped = 0
    existing = {t.source_text for t in g.terms}
    for row in reader:
        if len(row) < 2 or not row[0].strip():
            skipped += 1
            continue
        if row[0].strip().lower() in ("source", "source_text"):  # header
            continue
        if row[0] in existing:
            skipped += 1
            continue
        variants = [v.strip() for v in row[2].split("|") if v.strip()] if len(row) > 2 else []
        db.add(M.GlossaryTerm(glossary_id=g.id, source_text=row[0].strip(),
                              target_text=row[1].strip(),
                              spoken_variants_json=variants,
                              notes=row[3].strip() if len(row) > 3 else ""))
        existing.add(row[0])
        added += 1
    g.version += 1
    await db.commit()
    return {"added": added, "skipped": skipped, "version": g.version}


@router.get("/glossaries/{glossary_id}/export", response_class=PlainTextResponse)
async def export_glossary(glossary_id: uuid.UUID,
                          principal: Principal = Depends(require_org_user),
                          db: AsyncSession = Depends(get_db)):
    g = await _get_glossary(db, glossary_id, principal)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["source_text", "target_text", "spoken_variants", "notes"])
    for t in g.terms:
        w.writerow([t.source_text, t.target_text,
                    "|".join(t.spoken_variants_json or []), t.notes])
    return PlainTextResponse(
        buf.getvalue(),
        headers={"Content-Disposition":
                 f'attachment; filename="glossary_{g.name.replace(" ", "_")}_v{g.version}.csv"'})


# --------------------------------------------------------------------------- #
# Translation memories
# --------------------------------------------------------------------------- #

@router.post("/translation-memories", response_model=TMOut, status_code=201)
async def create_tm(body: TMCreate, principal: Principal = Depends(require_org_user),
                    db: AsyncSession = Depends(get_db)):
    principal.require("manage_tm")
    tm = M.TranslationMemory(org_id=principal.org_id, name=body.name,
                             source_lang=body.source_lang,
                             target_lang=body.target_lang, domain=body.domain)
    db.add(tm)
    await db.commit()
    return TMOut.model_validate(tm)


@router.get("/translation-memories", response_model=list[TMOut])
async def list_tms(principal: Principal = Depends(require_org_user),
                   db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(M.TranslationMemory).where(
        M.TranslationMemory.org_id == principal.org_id)
        .order_by(M.TranslationMemory.created_at.desc()))
    return [TMOut.model_validate(t) for t in res.scalars().all()]


async def _get_tm(db, tm_id, principal) -> M.TranslationMemory:
    tm = await db.get(M.TranslationMemory, tm_id)
    if tm is None or tm.org_id != principal.org_id:
        raise NotFoundError("Translation memory not found.")
    return tm


# --------------------------------------------------------------------------- #
# Entries (the pairs a reviewer curates).
#
# These are declared BEFORE the `/{tm_id}` routes on purpose: FastAPI matches
# in declaration order, and "/translation-memories/entries" would otherwise be
# swallowed by "/translation-memories/{tm_id}/entries" with a UUID parse
# error. The editor page used to read the *memory list* where it expected
# entries, which rendered empty languages, "confidence NaN%" and a Delete
# button that removed a whole memory (2026-10-21).
# --------------------------------------------------------------------------- #
def _entry_detail(e: M.TranslationMemoryEntry, tm: M.TranslationMemory) -> dict:
    return {
        "id": e.id,
        "source_text": e.source_text,
        "target_text": e.target_text,
        "approved": e.approved,
        "confidence": e.confidence,
        "usage_count": e.usage_count,
        "tm_id": tm.id,
        "tm_name": tm.name,
        "source_language": tm.source_lang,
        "target_language": tm.target_lang,
        "domain": e.domain or tm.domain,
        "version": e.version,
        "created_at": e.created_at,
    }


@router.get("/translation-memories/entries", response_model=list[TMEntryDetail])
async def list_tm_entries_all(principal: Principal = Depends(require_org_user),
                              db: AsyncSession = Depends(get_db),
                              q: str | None = Query(default=None, max_length=200),
                              limit: int = Query(default=200, le=1000)):
    """Every stored pair of the organization, newest first, optionally filtered
    by a search term over the source text."""
    principal.require("manage_tm")
    stmt = (
        select(M.TranslationMemoryEntry, M.TranslationMemory)
        .join(M.TranslationMemory, M.TranslationMemory.id == M.TranslationMemoryEntry.tm_id)
        .where(M.TranslationMemory.org_id == principal.org_id)
        .order_by(M.TranslationMemoryEntry.created_at.desc())
        .limit(limit)
    )
    if q:
        stmt = stmt.where(M.TranslationMemoryEntry.source_text.ilike(f"%{q}%"))
    res = await db.execute(stmt)
    return [_entry_detail(e, tm) for e, tm in res.all()]


@router.post("/translation-memories/entries", response_model=TMEntryDetail,
             status_code=201)
async def create_tm_entry_any(body: TMEntryCreate,
                               principal: Principal = Depends(require_org_user),
                               db: AsyncSession = Depends(get_db)):
    """Add a pair to a named memory (the first one when none is given)."""
    principal.require("manage_tm")
    if body.tm_id is not None:
        tm = await _get_tm(db, body.tm_id, principal)
    else:
        res = await db.execute(select(M.TranslationMemory).where(
            M.TranslationMemory.org_id == principal.org_id)
            .order_by(M.TranslationMemory.created_at.asc()).limit(1))
        tm = res.scalars().first()
        if tm is None:
            raise ValidationError("Create a translation memory first.")
    from app.services.translation_service import tm_store
    entry = await tm_store(db, tm.id, body.source_text, body.target_text,
                            tm.source_lang, tm.target_lang,
                            body.domain or tm.domain, body.approved,
                            principal.user_id)
    await db.refresh(entry)
    return _entry_detail(entry, tm)


@router.put("/translation-memories/entries/{entry_id}", response_model=TMEntryDetail)
async def update_tm_entry(entry_id: uuid.UUID, body: TMEntryUpdate,
                          principal: Principal = Depends(require_org_user),
                          db: AsyncSession = Depends(get_db)):
    """Edit a stored pair. Every edit bumps the entry version."""
    principal.require("manage_tm")
    entry, tm = await _get_tm_entry(db, entry_id, principal)
    if body.target_text is not None:
        entry.target_text = body.target_text
    if body.approved is not None:
        entry.approved = body.approved
    entry.version = (entry.version or 1) + 1
    await db.commit()
    await db.refresh(entry)
    return _entry_detail(entry, tm)


@router.delete("/translation-memories/entries/{entry_id}", status_code=204)
async def delete_tm_entry(entry_id: uuid.UUID,
                          principal: Principal = Depends(require_org_user),
                          db: AsyncSession = Depends(get_db)):
    """Delete one stored pair (not the memory that holds it)."""
    principal.require("manage_tm")
    entry, _tm = await _get_tm_entry(db, entry_id, principal)
    await db.delete(entry)
    await db.commit()
    return None


@router.get("/translation-memories/entries/export", response_class=PlainTextResponse)
async def export_tm_entries(principal: Principal = Depends(require_org_user),
                            db: AsyncSession = Depends(get_db)):
    """CSV export of the organization's pairs (parity with glossary export)."""
    principal.require("manage_tm")
    res = await db.execute(
        select(M.TranslationMemoryEntry, M.TranslationMemory)
        .join(M.TranslationMemory, M.TranslationMemory.id == M.TranslationMemoryEntry.tm_id)
        .where(M.TranslationMemory.org_id == principal.org_id)
        .order_by(M.TranslationMemoryEntry.created_at.desc()))
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["source_text", "target_text", "source_language",
                     "target_language", "domain", "approved", "memory"])
    for e, tm in res.all():
        writer.writerow([e.source_text, e.target_text, tm.source_lang,
                         tm.target_lang, e.domain or tm.domain,
                         "1" if e.approved else "0", tm.name])
    return out.getvalue()


async def _get_tm_entry(db, entry_id, principal):
    res = await db.execute(
        select(M.TranslationMemoryEntry, M.TranslationMemory)
        .join(M.TranslationMemory, M.TranslationMemory.id == M.TranslationMemoryEntry.tm_id)
        .where(M.TranslationMemoryEntry.id == entry_id,
               M.TranslationMemory.org_id == principal.org_id))
    row = res.first()
    if row is None:
        raise NotFoundError("Translation memory entry not found.")
    return row[0], row[1]


@router.post("/translation-memories/{tm_id}/entries", response_model=TMEntryOut,
             status_code=201)
async def add_tm_entry(tm_id: uuid.UUID, body: TMEntryIn,
                       principal: Principal = Depends(require_org_user),
                       db: AsyncSession = Depends(get_db)):
    principal.require("manage_tm")
    tm = await _get_tm(db, tm_id, principal)
    from app.services.translation_service import tm_store
    entry = await tm_store(db, tm.id, body.source_text, body.target_text,
                           tm.source_lang, tm.target_lang,
                           body.domain or tm.domain, body.approved,
                           principal.user_id)
    return TMEntryOut.model_validate(entry)


@router.get("/translation-memories/{tm_id}/entries", response_model=list[TMEntryOut])
async def list_tm_entries(tm_id: uuid.UUID,
                          principal: Principal = Depends(require_org_user),
                          db: AsyncSession = Depends(get_db),
                          limit: int = Query(default=100, le=500)):
    tm = await _get_tm(db, tm_id, principal)
    res = await db.execute(select(M.TranslationMemoryEntry).where(
        M.TranslationMemoryEntry.tm_id == tm.id)
        .order_by(M.TranslationMemoryEntry.created_at.desc()).limit(limit))
    return [TMEntryOut.model_validate(e) for e in res.scalars().all()]


@router.post("/translation-memories/{tm_id}/import", response_model=dict)
async def import_tm(tm_id: uuid.UUID, file: UploadFile,
                    principal: Principal = Depends(require_org_user),
                    db: AsyncSession = Depends(get_db)):
    """CSV/TSV import: source_text<TAB or ,>target_text"""
    principal.require("manage_tm")
    tm = await _get_tm(db, tm_id, principal)
    data = (await file.read()).decode("utf-8-sig", errors="replace")
    from app.services.translation_service import tm_store
    delim = "\t" if "\t" in data.splitlines()[0] else ","
    reader = csv.reader(io.StringIO(data), delimiter=delim)
    added = 0
    for row in reader:
        if len(row) < 2 or not row[0].strip() or row[0].strip().lower() == "source_text":
            continue
        await tm_store(db, tm.id, row[0].strip(), row[1].strip(),
                       tm.source_lang, tm.target_lang, tm.domain,
                       approved=False, created_by=principal.user_id,
                       with_embedding=False)
        added += 1
    return {"added": added}


@router.delete("/translation-memories/{tm_id}", status_code=204)
async def delete_tm(tm_id: uuid.UUID, principal: Principal = Depends(require_org_user),
                    db: AsyncSession = Depends(get_db)):
    principal.require("manage_tm")
    tm = await _get_tm(db, tm_id, principal)
    await db.delete(tm)
    await db.commit()


# --------------------------------------------------------------------------- #
# Style profiles
# --------------------------------------------------------------------------- #

@router.get("/style-profiles", response_model=list[StyleProfileOut])
async def list_styles(principal: Principal = Depends(require_org_user),
                      db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(M.StyleProfile).where(
        M.StyleProfile.status == "active",
        (M.StyleProfile.org_id.is_(None)) |
        (M.StyleProfile.org_id == principal.org_id))
        .order_by(M.StyleProfile.name))
    return [StyleProfileOut.model_validate(s) for s in res.scalars().all()]


@router.post("/style-profiles", response_model=StyleProfileOut, status_code=201)
async def create_style(body: StyleProfileCreate,
                       principal: Principal = Depends(require_org_user),
                       db: AsyncSession = Depends(get_db)):
    principal.require("manage_styles")
    sp = M.StyleProfile(org_id=principal.org_id, name=body.name, kind=body.kind,
                        config_json=body.config)
    db.add(sp)
    await db.commit()
    return StyleProfileOut.model_validate(sp)


@router.put("/style-profiles/{sp_id}", response_model=StyleProfileOut)
async def update_style(sp_id: uuid.UUID, body: StyleProfileCreate,
                       principal: Principal = Depends(require_org_user),
                       db: AsyncSession = Depends(get_db)):
    principal.require("manage_styles")
    sp = await db.get(M.StyleProfile, sp_id)
    if sp is None or (sp.org_id != principal.org_id):
        raise NotFoundError("Style profile not found (system profiles are read-only).")
    sp.name = body.name
    sp.kind = body.kind
    sp.config_json = body.config
    sp.version += 1   # versioned on every change (PDD §18)
    await db.commit()
    return StyleProfileOut.model_validate(sp)


@router.delete("/style-profiles/{sp_id}", status_code=204)
async def delete_style(sp_id: uuid.UUID,
                       principal: Principal = Depends(require_org_user),
                       db: AsyncSession = Depends(get_db)):
    principal.require("manage_styles")
    sp = await db.get(M.StyleProfile, sp_id)
    if sp is None or sp.org_id != principal.org_id:
        raise NotFoundError("Style profile not found.")
    sp.status = "archived"
    await db.commit()
