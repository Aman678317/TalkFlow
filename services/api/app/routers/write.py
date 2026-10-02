"""Desi Write & Dictionary API router."""
from __future__ import annotations

import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.deps import Principal, get_principal_optional
from app.schemas import DictionaryRequest, DictionaryResponse, WriteRequest, WriteResponse
from app.services import write_service

log = logging.getLogger("app.routers.write")

router = APIRouter(prefix="/api/v1", tags=["write"])


@router.post("/write", response_model=WriteResponse)
async def improve_text(
    body: WriteRequest,
    principal: Principal | None = Depends(get_principal_optional),
    db: AsyncSession = Depends(get_db),
):
    """Desi Write equivalent: rewrites text, fixes grammar/punctuation, adjusts tone and generates diffs."""
    return write_service.improve_text(
        text=body.text,
        language=body.language,
        style=body.style,
        tone=body.tone,
        corrections_only=body.corrections_only,
    )


@router.post("/dictionary", response_model=DictionaryResponse)
async def lookup_dictionary(
    body: DictionaryRequest,
    principal: Principal | None = Depends(get_principal_optional),
    db: AsyncSession = Depends(get_db),
):
    """Desi Dictionary equivalent: returns POS, definitions, synonyms and examples for words."""
    return write_service.lookup_dictionary(
        word=body.word,
        source_lang=body.source_lang,
        target_lang=body.target_lang,
    )
