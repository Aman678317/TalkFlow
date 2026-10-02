"""Text translation, language detection, and history routes (sections 14/47)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from globaltalk.core.config import settings
from globaltalk.core.db import get_db
from globaltalk.core.deps import Principal, get_principal, require_permission
from globaltalk.core.errors import NotFoundError
from globaltalk.core.ratelimit import Limit, check_rate_limit
from globaltalk.models import TranslationHistory
from globaltalk.schemas import (BatchTranslateRequest, BatchTranslateResponse, DetectRequest,
                                DetectResponse, HistoryItem, TranslateRequest,
                                TranslateResponse)
from globaltalk.services.translation import TranslateOptions, detect_text_language, translate_text

router = APIRouter(tags=["translation"])
TR_LIMIT = Limit.parse(settings.rate_limit_translate)


def _limit_key(p: Principal, request: Request) -> str:
    return f"tr:{p.api_key.id if p.api_key else p.user_id}"


@router.post("/translate", response_model=TranslateResponse)
def translate(body: TranslateRequest, request: Request,
              principal: Principal = Depends(require_permission("translate")),
              db: Session = Depends(get_db)):
    check_rate_limit(_limit_key(principal, request), TR_LIMIT)
    outcome = translate_text(
        db, org_id=principal.org_id, text=body.text,
        opts=TranslateOptions(source_language=body.source_language,
                              target_language=body.target_language,
                              glossary_id=body.glossary_id,
                              style_profile_id=body.style_profile_id,
                              translation_memory_id=body.translation_memory_id,
                              domain=body.domain, intent=body.intent),
        user_id=principal.user_id,
        api_key_id=principal.api_key.id if principal.api_key else None)
    return TranslateResponse(
        translation_id=outcome.translation_id, source_language=outcome.source_language,
        target_language=outcome.target_language, source_text=outcome.source_text,
        translated_text=outcome.translated_text, model=outcome.model,
        provider=outcome.provider, latency_ms=round(outcome.latency_ms, 1),
        quality_flags=outcome.quality_flags, from_translation_memory=outcome.from_tm,
        detected_confidence=outcome.detected_confidence)


@router.post("/translate/batch", response_model=BatchTranslateResponse)
def translate_batch(body: BatchTranslateRequest, request: Request,
                    principal: Principal = Depends(require_permission("translate")),
                    db: Session = Depends(get_db)):
    check_rate_limit(_limit_key(principal, request), TR_LIMIT)
    out = []
    for text in body.texts:
        o = translate_text(
            db, org_id=principal.org_id, text=text,
            opts=TranslateOptions(source_language=body.source_language,
                                  target_language=body.target_language,
                                  glossary_id=body.glossary_id,
                                  style_profile_id=body.style_profile_id,
                                  domain=body.domain, intent=body.intent),
            user_id=principal.user_id,
            api_key_id=principal.api_key.id if principal.api_key else None,
            kind="batch")
        out.append(TranslateResponse(
            translation_id=o.translation_id, source_language=o.source_language,
            target_language=o.target_language, source_text=o.source_text,
            translated_text=o.translated_text, model=o.model, provider=o.provider,
            latency_ms=round(o.latency_ms, 1), quality_flags=o.quality_flags,
            from_translation_memory=o.from_tm, detected_confidence=o.detected_confidence))
    return BatchTranslateResponse(translations=out)


@router.post("/detect-language", response_model=DetectResponse)
def detect(body: DetectRequest, principal: Principal = Depends(get_principal),
           db: Session = Depends(get_db)):
    from ai.bootstrap import get_router
    from ai.interfaces import ProviderUnavailable
    from ai.model_router.router import RouteRequest
    try:
        result, route = get_router().execute(RouteRequest(task="langid"),
                                             lambda p: p.detect(body.text))
        return DetectResponse(language=result.language or "unknown",
                              confidence=round(result.confidence, 4),
                              provider=route.provider_name,
                              alternatives=[{"language": l, "confidence": round(c, 4)}
                                            for l, c in result.alternatives])
    except ProviderUnavailable:
        lang, conf = detect_text_language(db, body.text)
        return DetectResponse(language=lang, confidence=conf, provider="fallback")


@router.get("/history", response_model=list[HistoryItem])
def history(principal: Principal = Depends(get_principal), db: Session = Depends(get_db),
            limit: int = Query(default=50, le=200), offset: int = 0,
            q: str | None = None, source_language: str | None = None,
            target_language: str | None = None):
    query = db.query(TranslationHistory).filter(TranslationHistory.org_id == principal.org_id)
    if principal.api_key is None and principal.user_id:
        query = query.filter(TranslationHistory.user_id == principal.user_id)
    if q:
        query = query.filter(TranslationHistory.source_text.ilike(f"%{q}%")
                             | TranslationHistory.translated_text.ilike(f"%{q}%"))
    if source_language:
        query = query.filter(TranslationHistory.source_language == source_language)
    if target_language:
        query = query.filter(TranslationHistory.target_language == target_language)
    rows = (query.order_by(TranslationHistory.created_at.desc())
            .offset(offset).limit(limit).all())
    return [HistoryItem(id=r.id, created_at=r.created_at, source_language=r.source_language,
                        target_language=r.target_language, source_text=r.source_text,
                        translated_text=r.translated_text, model=r.model, provider=r.provider,
                        latency_ms=r.latency_ms, quality_flags=r.quality_flags or [],
                        kind=r.kind, from_tm=r.from_tm) for r in rows]


@router.delete("/history/{item_id}", status_code=204)
def delete_history(item_id: str, principal: Principal = Depends(get_principal),
                   db: Session = Depends(get_db)):
    row = (db.query(TranslationHistory)
           .filter(TranslationHistory.id == item_id,
                   TranslationHistory.org_id == principal.org_id).first())
    if not row:
        raise NotFoundError("History item not found")
    db.delete(row)
    db.commit()
