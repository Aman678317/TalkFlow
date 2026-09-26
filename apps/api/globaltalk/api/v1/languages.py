"""Languages capability registry routes + glossaries + translation memory + style profiles."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from globaltalk.core.db import get_db
from globaltalk.core.deps import Principal, get_principal, require_permission
from globaltalk.core.errors import NotFoundError, ValidationError
from globaltalk.core.flags import flag_enabled
from globaltalk.models import (Glossary, GlossaryTerm, LanguageCapability, StyleProfile,
                               TranslationMemory)
from globaltalk.schemas import (GlossaryCreate, GlossaryOut, GlossaryTermIn, LanguageOut,
                                StyleProfileIn, StyleProfileOut, TmEntryIn, TmEntryOut)
from globaltalk.services import capabilities as caps
from globaltalk.services.translation import tm_hash, tm_store

router = APIRouter(tags=["languages"])

# ------------------------------------------------------------------ languages

@router.get("/languages", response_model=list[LanguageOut])
def list_languages(db: Session = Depends(get_db),
                   principal: Principal = Depends(get_principal),
                   include_experimental: bool = True):
    rows = caps.list_capabilities(db, include_experimental=include_experimental)
    if not include_experimental and not flag_enabled(db, "experimental_language",
                                                     principal.org_id):
        rows = [r for r in rows if r.mt_status != "EXPERIMENTAL"]
    return [LanguageOut.model_validate(r) for r in rows]


@router.post("/languages/refresh")
def refresh_languages(principal: Principal = Depends(require_permission("manage_security")),
                      db: Session = Depends(get_db)):
    report = caps.refresh_from_providers(db)
    return {"refreshed": len(report), "report": report}


@router.get("/languages/pairs")
def pair_matrix(db: Session = Depends(get_db),
                principal: Principal = Depends(get_principal)):
    rows = caps.list_capabilities(db)
    supported = [r.code for r in rows if r.translation_supported]
    return {"translatable_languages": supported,
            "note": "Every pair is translated directly from the canonical source; "
                    "pivot use is flagged per section 77.10."}


# ------------------------------------------------------------------ glossaries

glossary_router = APIRouter(prefix="/glossaries", tags=["glossaries"])


@glossary_router.get("", response_model=list[GlossaryOut])
def list_glossaries(principal: Principal = Depends(get_principal),
                    db: Session = Depends(get_db)):
    rows = (db.query(Glossary).filter(Glossary.org_id == principal.org_id)
            .order_by(Glossary.created_at.desc()).all())
    return [GlossaryOut(id=g.id, name=g.name, source_language=g.source_language,
                        target_language=g.target_language, version=g.version, status=g.status,
                        domain=g.domain, term_count=len(g.terms), created_at=g.created_at)
            for g in rows]


def _get_glossary(db: Session, gid: str, org_id: str) -> Glossary:
    g = db.query(Glossary).filter(Glossary.id == gid, Glossary.org_id == org_id).first()
    if not g:
        raise NotFoundError("Glossary not found")
    return g


@glossary_router.post("", response_model=GlossaryOut, status_code=201)
def create_glossary(body: GlossaryCreate,
                    principal: Principal = Depends(require_permission("manage_glossaries")),
                    db: Session = Depends(get_db)):
    g = Glossary(org_id=principal.org_id, name=body.name, source_language=body.source_language,
                 target_language=body.target_language, domain=body.domain,
                 description=body.description, created_by=principal.user_id)
    db.add(g)
    db.commit()
    return GlossaryOut(id=g.id, name=g.name, source_language=g.source_language,
                       target_language=g.target_language, version=g.version, status=g.status,
                       domain=g.domain, term_count=0, created_at=g.created_at)


@glossary_router.get("/{gid}")
def get_glossary(gid: str, principal: Principal = Depends(get_principal),
                 db: Session = Depends(get_db)):
    g = _get_glossary(db, gid, principal.org_id)
    return {"id": g.id, "name": g.name, "source_language": g.source_language,
            "target_language": g.target_language, "version": g.version, "status": g.status,
            "domain": g.domain, "description": g.description,
            "terms": [{"id": t.id, "source_term": t.source_term, "target_term": t.target_term,
                       "part_of_speech": t.part_of_speech,
                       "case_sensitive": t.case_sensitive,
                       "do_not_translate": t.do_not_translate,
                       "spoken_variants": t.spoken_variants or []} for t in g.terms]}


@glossary_router.post("/{gid}/terms", status_code=201)
def add_term(gid: str, body: GlossaryTermIn,
             principal: Principal = Depends(require_permission("manage_glossaries")),
             db: Session = Depends(get_db)):
    g = _get_glossary(db, gid, principal.org_id)
    if g.status == "archived":
        raise ValidationError("Cannot modify an archived glossary", code="glossary_archived")
    t = GlossaryTerm(glossary_id=g.id, source_term=body.source_term,
                     source_lower=body.source_term.lower(), target_term=body.target_term,
                     part_of_speech=body.part_of_speech, case_sensitive=body.case_sensitive,
                     do_not_translate=body.do_not_translate,
                     spoken_variants=body.spoken_variants)
    db.add(t)
    g.version += 1  # glossaries are versioned; realtime stores the version used
    db.commit()
    return {"id": t.id, "version": g.version}


@glossary_router.delete("/{gid}/terms/{term_id}", status_code=204)
def delete_term(gid: str, term_id: str,
                principal: Principal = Depends(require_permission("manage_glossaries")),
                db: Session = Depends(get_db)):
    g = _get_glossary(db, gid, principal.org_id)
    t = db.query(GlossaryTerm).filter(GlossaryTerm.id == term_id,
                                      GlossaryTerm.glossary_id == g.id).first()
    if not t:
        raise NotFoundError("Term not found")
    db.delete(t)
    g.version += 1
    db.commit()


@glossary_router.post("/{gid}/activate")
def activate_glossary(gid: str,
                      principal: Principal = Depends(require_permission("manage_glossaries")),
                      db: Session = Depends(get_db)):
    g = _get_glossary(db, gid, principal.org_id)
    if not g.terms:
        raise ValidationError("Cannot activate an empty glossary", code="glossary_empty")
    g.status = "active"
    db.commit()
    return {"id": g.id, "status": g.status, "version": g.version}


@glossary_router.post("/{gid}/archive")
def archive_glossary(gid: str,
                     principal: Principal = Depends(require_permission("manage_glossaries")),
                     db: Session = Depends(get_db)):
    g = _get_glossary(db, gid, principal.org_id)
    g.status = "archived"
    db.commit()
    return {"id": g.id, "status": g.status}


@glossary_router.post("/{gid}/import")
def import_glossary(gid: str, file_content: str = Query(default=None),
                    csv_text: str | None = None,
                    principal: Principal = Depends(require_permission("manage_glossaries")),
                    db: Session = Depends(get_db)):
    """CSV import: source_term,target_term[,pos[,do_not_translate]]"""
    g = _get_glossary(db, gid, principal.org_id)
    text = file_content or csv_text
    if not text:
        raise ValidationError("Provide csv_text", code="csv_required")
    reader = csv.reader(io.StringIO(text))
    added = 0
    for row in reader:
        if len(row) < 2 or not row[0].strip():
            continue
        if row[0].strip().lower() == "source_term":
            continue
        db.add(GlossaryTerm(glossary_id=g.id, source_term=row[0].strip(),
                            source_lower=row[0].strip().lower(), target_term=row[1].strip(),
                            part_of_speech=row[2].strip() if len(row) > 2 else "",
                            do_not_translate=(len(row) > 3
                                              and row[3].strip().lower() in ("1", "true"))))
        added += 1
    g.version += 1
    db.commit()
    return {"imported": added, "version": g.version}


@glossary_router.get("/{gid}/export")
def export_glossary(gid: str, principal: Principal = Depends(get_principal),
                    db: Session = Depends(get_db)):
    g = _get_glossary(db, gid, principal.org_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["source_term", "target_term", "pos", "do_not_translate"])
    for t in g.terms:
        w.writerow([t.source_term, t.target_term, t.part_of_speech, t.do_not_translate])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"content-disposition": f'attachment; filename="{g.name}.csv"'})


# ------------------------------------------------------------------ translation memory

tm_router = APIRouter(prefix="/translation-memories", tags=["translation-memory"])


@tm_router.get("", response_model=list[TmEntryOut])
def list_tm(principal: Principal = Depends(get_principal), db: Session = Depends(get_db),
            limit: int = Query(default=100, le=500), source_language: str | None = None,
            target_language: str | None = None, q: str | None = None):
    query = db.query(TranslationMemory).filter(TranslationMemory.org_id == principal.org_id)
    if source_language:
        query = query.filter(TranslationMemory.source_language == source_language)
    if target_language:
        query = query.filter(TranslationMemory.target_language == target_language)
    if q:
        query = query.filter(TranslationMemory.source_text.ilike(f"%{q}%"))
    rows = query.order_by(TranslationMemory.created_at.desc()).limit(limit).all()
    return [TmEntryOut(id=r.id, source_text=r.source_text, target_text=r.target_text,
                       source_language=r.source_language, target_language=r.target_language,
                       domain=r.domain, approved=r.approved, confidence=r.confidence,
                       usage_count=r.usage_count, version=r.version, created_at=r.created_at)
            for r in rows]


@tm_router.post("", response_model=TmEntryOut, status_code=201)
def add_tm(body: TmEntryIn,
           principal: Principal = Depends(require_permission("manage_translation_memory")),
           db: Session = Depends(get_db)):
    row = tm_store(db, principal.org_id, body.source_text, body.target_text,
                   body.source_language, body.target_language, domain=body.domain,
                   approved=body.approved, created_by=principal.user_id)
    return TmEntryOut(id=row.id, source_text=row.source_text, target_text=row.target_text,
                      source_language=row.source_language, target_language=row.target_language,
                      domain=row.domain, approved=row.approved, confidence=row.confidence,
                      usage_count=row.usage_count, version=row.version, created_at=row.created_at)


@tm_router.delete("/{tm_id}", status_code=204)
def delete_tm(tm_id: str,
              principal: Principal = Depends(require_permission("manage_translation_memory")),
              db: Session = Depends(get_db)):
    row = (db.query(TranslationMemory)
           .filter(TranslationMemory.id == tm_id,
                   TranslationMemory.org_id == principal.org_id).first())
    if not row:
        raise NotFoundError("TM entry not found")
    db.delete(row)
    db.commit()


# ------------------------------------------------------------------ style profiles

style_router = APIRouter(prefix="/style-profiles", tags=["style-profiles"])


@style_router.get("", response_model=list[StyleProfileOut])
def list_styles(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    rows = (db.query(StyleProfile)
            .filter(StyleProfile.is_system.is_(True)
                    | (StyleProfile.org_id == principal.org_id)).all())
    return [StyleProfileOut(id=r.id, name=r.name, kind=r.kind, version=r.version,
                            rules=r.rules or {}, prompt_fragment=r.prompt_fragment,
                            is_system=r.is_system) for r in rows]


@style_router.post("", response_model=StyleProfileOut, status_code=201)
def create_style(body: StyleProfileIn,
                 principal: Principal = Depends(require_permission("manage_style_profiles")),
                 db: Session = Depends(get_db)):
    sp = StyleProfile(org_id=principal.org_id, name=body.name, kind=body.kind,
                      rules=body.rules, prompt_fragment=body.prompt_fragment)
    db.add(sp)
    db.commit()
    return StyleProfileOut(id=sp.id, name=sp.name, kind=sp.kind, version=sp.version,
                           rules=sp.rules, prompt_fragment=sp.prompt_fragment,
                           is_system=False)


@style_router.put("/{sp_id}", response_model=StyleProfileOut)
def update_style(sp_id: str, body: StyleProfileIn,
                 principal: Principal = Depends(require_permission("manage_style_profiles")),
                 db: Session = Depends(get_db)):
    sp = (db.query(StyleProfile)
          .filter(StyleProfile.id == sp_id, StyleProfile.org_id == principal.org_id).first())
    if not sp:
        raise NotFoundError("Style profile not found (system profiles are immutable)")
    sp.name, sp.kind = body.name, body.kind
    sp.rules, sp.prompt_fragment = body.rules, body.prompt_fragment
    sp.version += 1  # versioned: segments store the version applied
    db.commit()
    return StyleProfileOut(id=sp.id, name=sp.name, kind=sp.kind, version=sp.version,
                           rules=sp.rules, prompt_fragment=sp.prompt_fragment,
                           is_system=sp.is_system)


@style_router.delete("/{sp_id}", status_code=204)
def delete_style(sp_id: str,
                 principal: Principal = Depends(require_permission("manage_style_profiles")),
                 db: Session = Depends(get_db)):
    sp = (db.query(StyleProfile)
          .filter(StyleProfile.id == sp_id, StyleProfile.org_id == principal.org_id).first())
    if not sp:
        raise NotFoundError("Style profile not found")
    db.delete(sp)
    db.commit()
