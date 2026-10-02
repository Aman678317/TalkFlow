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
    StyleProfileOut, TMCreate, TMEntryIn, TMEntryOut, TMOut,
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
