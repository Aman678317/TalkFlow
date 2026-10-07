"""Translation service — the core text translation pipeline (PDD §10).

Flow:
 1. detect source language (when AUTO)
 2. normalize unicode / protect spans
 3. translation memory lookup (exact -> fuzzy -> semantic) BEFORE model
 4. glossary load (term constraints + spoken variants)
 5. style profile load
 6. model route via AIFacade (intent + capability + health)
 7. post-QA (numbers/urls/script/glossary checks)
 8. persist translation record + usage metering
 9. optional TM write-back of approved results

The SAME pipeline is reused by: REST /translate, realtime fan-out, chat
translation, document segments, and the agent bridge — no duplicated
business logic (PDD §72).
"""
from __future__ import annotations

import contextlib
import hashlib
import logging
import re
import time
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import context
from app.ai import ai
from app.db import models as M
from app.errors import UnsupportedLanguageError, ValidationError
from app.services import usage_service
from gt_ai.embeddings.hash_tfidf import cosine_similarity
from gt_ai.translation.text_ops import (
    apply_glossary_to_output,
    normalize_unicode,
    quality_checks,
)
from gt_ai.types import Intent, TranslationRequest, TranslationResult

log = logging.getLogger("app.translation")

MAX_TEXT_LEN = 50_000
_WORD_RX = re.compile(r"[\w']+", re.UNICODE)


@dataclass
class TranslateContext:
    org_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    api_key_id: uuid.UUID | None = None
    glossary_id: uuid.UUID | None = None
    style_profile_id: uuid.UUID | None = None
    tm_id: uuid.UUID | None = None
    domain: str = "general"
    intent: str = "quality_optimized"
    formality: str = "default"
    product: str = "text"          # text|document|realtime|chat
    meeting_id: uuid.UUID | None = None
    segment_id: uuid.UUID | None = None
    persist: bool = True
    meter: bool = True
    tm_writeback: bool = False     # store model result into TM (approved flows)
    extra_flags: list[str] = field(default_factory=list)


@dataclass
class TranslateOutput:
    result: TranslationResult
    translation_id: uuid.UUID
    tm_match: str | None          # exact|fuzzy|semantic|None
    source_lang: str


def normalize_for_match(text: str) -> str:
    t = normalize_unicode(text).strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def _normalized_hash(text: str) -> str:
    return hashlib.sha256(normalize_for_match(text).encode()).hexdigest()[:64]


def _lexical_similarity(a: str, b: str) -> float:
    """Dice coefficient over word bigrams — script-agnostic fuzzy matching."""
    def bigrams(s: str) -> set:
        words = _WORD_RX.findall(normalize_for_match(s))
        return {tuple(words[i:i + 2]) for i in range(len(words) - 1)} or {tuple(words)}
    A, B = bigrams(a), bigrams(b)
    if not A or not B:
        return 0.0
    return 2 * len(A & B) / (len(A) + len(B))


# --------------------------------------------------------------------------- #
# Capability validation
# --------------------------------------------------------------------------- #

async def validate_pair(db: AsyncSession, source_lang: str, target_lang: str,
                        *, need_speech_in: bool = False, need_speech_out: bool = False,
                        need_realtime: bool = False) -> M.LanguageCapability:
    tgt = await db.get(M.LanguageCapability, target_lang)
    if tgt is None:
        raise UnsupportedLanguageError(
            f"Target language '{target_lang}' is not in the capability registry.")
    if tgt.translation_status == "EXPERIMENTAL":
        raise UnsupportedLanguageError(
            f"Translation into '{target_lang}' is experimental and not enabled.")
    if need_speech_in and source_lang not in ("auto", ""):
        src = await db.get(M.LanguageCapability, source_lang)
        if src is None or src.speech_input_status == "EXPERIMENTAL":
            raise UnsupportedLanguageError(
                f"Speech input for '{source_lang}' is not supported yet.")
    if need_speech_out and tgt.speech_output_status == "EXPERIMENTAL":
        raise UnsupportedLanguageError(
            f"Speech output for '{target_lang}' is not supported yet. "
            "Captions remain available.", recoverable=True)
    if need_realtime and tgt.realtime_status == "EXPERIMENTAL":
        raise UnsupportedLanguageError(
            f"Realtime translation into '{target_lang}' is not enabled.")
    return tgt


# --------------------------------------------------------------------------- #
# TM lookup
# --------------------------------------------------------------------------- #

async def _tm_lookup(db: AsyncSession, tm_id: uuid.UUID, text: str,
                     source_lang: str, target_lang: str, domain: str):
    """Returns (entry, match_type, score) or None."""
    norm_hash = _normalized_hash(text)
    res = await db.execute(
        select(M.TranslationMemoryEntry).where(
            M.TranslationMemoryEntry.tm_id == tm_id,
            M.TranslationMemoryEntry.source_normalized == norm_hash,
            M.TranslationMemoryEntry.source_lang == source_lang,
            M.TranslationMemoryEntry.target_lang == target_lang).limit(1))
    entry = res.scalars().first()
    if entry is not None and entry.approved:
        return entry, "exact", 1.0

    # fuzzy: lexical over candidate rows (bounded scan), then semantic
    res = await db.execute(
        select(M.TranslationMemoryEntry).where(
            M.TranslationMemoryEntry.tm_id == tm_id,
            M.TranslationMemoryEntry.source_lang == source_lang,
            M.TranslationMemoryEntry.target_lang == target_lang,
            M.TranslationMemoryEntry.domain == domain).limit(2000))
    candidates = res.scalars().all()
    best = None
    best_score = 0.0
    for c in candidates:
        score = _lexical_similarity(text, c.source_text)
        if score > best_score:
            best, best_score = c, score
    if best is not None and best_score >= 0.85 and best.approved:
        return best, "fuzzy", best_score
    # semantic pass via embeddings (only for promising candidates)
    if best is not None and best_score >= 0.5 and best.embedding_json and best.approved:
        try:
            q_emb = (await ai.embed([text]))[0]
            sim = cosine_similarity(q_emb, best.embedding_json)
            if sim >= 0.88:
                return best, "semantic", sim
        except Exception as e:
            log.debug("semantic TM match skipped: %s", e)
    return None


# --------------------------------------------------------------------------- #
# Glossary / style loading
# --------------------------------------------------------------------------- #

async def load_glossary(db: AsyncSession, glossary_id: uuid.UUID,
                        source_lang: str, target_lang: str) -> tuple[M.Glossary, dict[str, str], dict[str, str]] | None:
    g = await db.get(M.Glossary, glossary_id)
    if g is None or g.status == "archived":
        return None
    # glossary applies when its declared pair matches (or is language-agnostic)
    if g.source_lang not in (source_lang, "auto") or g.target_lang not in (target_lang, "auto"):
        return None
    terms: dict[str, str] = {}
    spoken: dict[str, str] = {}
    for t in g.terms:
        terms[t.source_text] = t.target_text
        for v in (t.spoken_variants_json or []):
            spoken[v] = t.source_text
    return g, terms, spoken


async def load_style(db: AsyncSession, style_profile_id: uuid.UUID | None) -> dict | None:
    if style_profile_id is None:
        return None
    sp = await db.get(M.StyleProfile, style_profile_id)
    if sp is None or sp.status != "active":
        return None
    return dict(sp.config_json or {})


# --------------------------------------------------------------------------- #
# Main entry
# --------------------------------------------------------------------------- #

async def translate_text(
    db: AsyncSession, text: str, source_language: str, target_language: str,
    ctx: TranslateContext,
) -> TranslateOutput:
    if not text or not text.strip():
        raise ValidationError("Text must not be empty.")
    if len(text) > MAX_TEXT_LEN:
        raise ValidationError(f"Text exceeds {MAX_TEXT_LEN} characters.")

    t0 = time.perf_counter()
    source_language = (source_language or "AUTO").lower()
    target_language = target_language.lower()
    if source_language == target_language and source_language != "auto":
        raise ValidationError("Source and target language must differ.")

    # 1) language detection ---------------------------------------------- #
    detected = source_language
    detect_conf = 1.0
    if source_language in ("auto", ""):
        det = await ai.detect_language(text)
        detected = det.language
        detect_conf = det.confidence
        log.debug("detected lang=%s conf=%.2f provider=%s",
                  det.language, det.confidence, det.provider)
    if detected == target_language:
        raise UnsupportedLanguageError(
            "Detected source language equals the target language.",
            details={"detected": detected}, recoverable=True)

    # 2) capability validation -------------------------------------------- #
    await validate_pair(db, detected, target_language)

    # 3) translation memory ------------------------------------------------ #
    tm_match = None
    if ctx.tm_id:
        hit = await _tm_lookup(db, ctx.tm_id, text, detected, target_language, ctx.domain)
        if hit:
            entry, tm_match, score = hit
            entry.usage_count += 1
            result = TranslationResult(
                text=entry.target_text, source_lang=detected, target_lang=target_language,
                model=f"tm/{tm_match}", provider="translation_memory",
                latency_ms=(time.perf_counter() - t0) * 1000,
                quality_flags=[f"tm_{tm_match}_match"], confidence=score)
            out = await _persist(db, text, result, ctx, tm_match=tm_match,
                                 tm_entry_id=entry.id, glossary=None)
            return out

    # 4) glossary + style --------------------------------------------------- #
    glossary_row = None
    glossary_terms: dict[str, str] = {}
    if ctx.glossary_id:
        loaded = await load_glossary(db, ctx.glossary_id, detected, target_language)
        if loaded:
            glossary_row, glossary_terms, _spoken = loaded
    style_cfg = await load_style(db, ctx.style_profile_id) or {}
    if ctx.formality and ctx.formality != "default":
        style_cfg["formality"] = ctx.formality

    # 5) translate via router ---------------------------------------------- #
    req = TranslationRequest(
        text=normalize_unicode(text),
        source_lang=detected,
        target_lang=target_language,
        domain=ctx.domain,
        intent=Intent(ctx.intent),
        glossary=glossary_terms or None,
        style=style_cfg,
    )
    result, decision = await ai.translate(req)

    import app.metrics as met
    with contextlib.suppress(Exception):
        met.TRANSLATION_LATENCY.labels(
            src=detected or "auto",
            tgt=target_language or "unknown",
            provider=decision.provider if decision else "unknown",
        ).observe(result.latency_ms)

    # 6) post-QA: glossary enforcement + protected span checks are applied
    #    inside providers; re-run cross-provider checks here for uniformity.
    result.text, extra_flags = apply_glossary_to_output(
        result.text, req.text, glossary_terms)
    for f in quality_checks(req.text, result.text):
        if f not in result.quality_flags:
            result.quality_flags.append(f)
    result.quality_flags.extend(ctx.extra_flags)
    if detect_conf < 0.5 and source_language in ("auto", ""):
        result.quality_flags.append("low_detection_confidence")

    # 7) persist + meter ----------------------------------------------------- #
    out = await _persist(db, text, result, ctx, tm_match=None,
                         glossary=glossary_row)

    # 8) optional TM write-back (approved flows only; never realtime partials)
    if ctx.tm_writeback and ctx.tm_id and "dev_provider" not in result.quality_flags \
            and not any(f.startswith(("number_mismatch", "empty_translation",
                                      "untranslated_output")) for f in result.quality_flags):
        await tm_store(db, ctx.tm_id, text, result.text, detected, target_language,
                       ctx.domain, approved=False, created_by=ctx.user_id)
    return out


async def _persist(db: AsyncSession, source_text: str, result: TranslationResult,
                   ctx: TranslateContext, *, tm_match: str | None,
                   tm_entry_id: uuid.UUID | None = None,
                   glossary: M.Glossary | None) -> TranslateOutput:
    translation_id = uuid.uuid4()
    try:
        if ctx.persist:
            db.add(M.TranslationSegment(
                id=translation_id,
                segment_id=ctx.segment_id,
                meeting_id=ctx.meeting_id,
                org_id=ctx.org_id,
                product=ctx.product,
                source_lang=result.source_lang,
                target_lang=result.target_lang,
                source_text=source_text,
                target_text=result.text,
                domain=ctx.domain,
                intent=ctx.intent,
                model=result.model,
                provider=result.provider,
                latency_ms=result.latency_ms,
                quality_flags_json=result.quality_flags,
                glossary_id=glossary.id if glossary else ctx.glossary_id,
                glossary_version=glossary.version if glossary else None,
                style_profile_id=ctx.style_profile_id,
                tm_id=ctx.tm_id if tm_match else None,
                tm_match_type=tm_match,
                created_by=ctx.user_id,
                char_count=len(source_text),
            ))
        if ctx.meter and ctx.org_id:
            await usage_service.record_usage(
                db, org_id=ctx.org_id, product=ctx.product, unit_type="characters",
                units=len(source_text), user_id=ctx.user_id, api_key_id=ctx.api_key_id,
                model_version=result.model, source_lang=result.source_lang,
                target_lang=result.target_lang,
                metadata={"provider": result.provider, "tm_match": tm_match,
                          "flags": result.quality_flags})
            await usage_service.record_usage(
                db, org_id=ctx.org_id, product=ctx.product,
                unit_type="translation_requests", units=1,
                user_id=ctx.user_id, api_key_id=ctx.api_key_id,
                source_lang=result.source_lang, target_lang=result.target_lang)
        await db.commit()
    except Exception as e:
        log.warning("failed to persist translation segment or record usage: %s", e)
        await db.rollback()
    return TranslateOutput(result=result, translation_id=translation_id,
                           tm_match=tm_match, source_lang=result.source_lang)


# --------------------------------------------------------------------------- #
# TM store (shared by API + write-back)
# --------------------------------------------------------------------------- #

async def tm_store(db: AsyncSession, tm_id: uuid.UUID, source_text: str,
                   target_text: str, source_lang: str, target_lang: str,
                   domain: str, approved: bool, created_by: uuid.UUID | None,
                   with_embedding: bool = True) -> M.TranslationMemoryEntry:
    embedding = None
    if with_embedding:
        try:
            embedding = (await ai.embed([normalize_for_match(source_text)]))[0]
        except Exception as e:
            log.debug("embedding for TM skipped: %s", e)
    entry = M.TranslationMemoryEntry(
        tm_id=tm_id, source_text=source_text, target_text=target_text,
        source_normalized=_normalized_hash(source_text),
        source_lang=source_lang, target_lang=target_lang, domain=domain,
        approved=approved, created_by=created_by,
        confidence=1.0 if approved else 0.7,
        embedding_json=embedding,
    )
    db.add(entry)
    await db.execute(
        M.TranslationMemory.__table__.update()
        .where(M.TranslationMemory.id == tm_id)
        .values(entry_count=M.TranslationMemory.entry_count + 1))
    await db.commit()
    return entry
