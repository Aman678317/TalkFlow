"""Neural Translation Engine coordinating normalization, TM, glossaries, routing, and finalization."""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional
from app.core.exceptions import ValidationError
from app.glossary.glossary_manager import glossary_manager
from app.memory.cache import translation_cache
from app.memory.translation_memory import translation_memory_service
from app.models.schemas import TranslationRequestSchema, TranslationResponseSchema
from app.providers.base import Intent, TranslationRequest, TranslationResult
from app.quality.protected_spans import SpanProtector
from app.routing.provider_router import provider_router
from app.translation.finalizer import finalize_translation
from app.translation.normalizer import normalize_source_text
from app.translation.translator import CodeSwitchTranslator

log = logging.getLogger("agent04.translation.engine")


class TranslationEngine:
    """Core translation pipeline for single and multi-target requests."""

    def __init__(self) -> None:
        self.router = provider_router

    async def translate_single(self, req: TranslationRequestSchema) -> TranslationResponseSchema:
        start_time = time.perf_counter()
        normalized_source = normalize_source_text(req.text)
        if not normalized_source:
            raise ValidationError("Canonical source text must be non-empty.")

        src = req.source_lang.lower().strip()
        tgt = req.target_lang.lower().strip()

        # 1. Same-language identity rule (src == tgt): return verbatim without invoking MT
        if src == tgt and src not in ("auto", ""):
            latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            return TranslationResponseSchema(
                session_id=req.session_id,
                conversation_id=req.conversation_id,
                speaker_id=req.speaker_id,
                utterance_id=req.utterance_id,
                segment_id=req.segment_id,
                source_lang=src,
                target_lang=tgt,
                text=normalized_source,
                is_final=True,
                provider="identity",
                model="source_equals_target",
                latency_ms=latency_ms,
                quality_flags=["source_equals_target"],
                source_equals_target=True,
            )

        # 2. Check translation cache for already-translated segment
        if req.segment_id:
            cached = translation_cache.get(req.segment_id, tgt)
            if cached:
                log.info(f"Serving segment {req.segment_id} target {tgt} from cache.")
                return cached

        # 3. Check approved Translation Memory (if tm_id provided)
        tm_match_type = None
        if req.tm_id:
            org_id = req.session_id or "default_tenant"
            tm_hit = translation_memory_service.lookup(
                org_id=org_id,
                tm_id=req.tm_id,
                source_text=normalized_source,
                source_lang=src,
                target_lang=tgt,
            )
            if tm_hit:
                latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
                res = TranslationResponseSchema(
                    session_id=req.session_id,
                    conversation_id=req.conversation_id,
                    speaker_id=req.speaker_id,
                    utterance_id=req.utterance_id,
                    segment_id=req.segment_id,
                    source_lang=src,
                    target_lang=tgt,
                    text=tm_hit.entry.target_text,
                    is_final=True,
                    provider="translation_memory",
                    model=f"tm-{tm_hit.match_type}",
                    latency_ms=latency_ms,
                    confidence=tm_hit.score,
                    quality_flags=[],
                    tm_match=tm_hit.match_type,
                )
                if req.segment_id:
                    translation_cache.put(req.segment_id, tgt, res)
                return res

        # 4. Protect immutable entities (URLs, emails, numbers, code)
        span_protector = SpanProtector()
        protected_text = span_protector.protect(normalized_source)

        # 5. Protect technical terms in code-switched / Hinglish text
        tech_protected: Dict[str, str] = {}
        if src in ("hi", "mr", "auto"):
            protected_text, tech_protected = CodeSwitchTranslator.protect_technical_spans(protected_text)

        # 6. Apply glossary pre-substitution
        glossary_protected: Dict[int, str] = {}
        glossary_applied = False
        if req.glossary:
            protected_text, glossary_protected = glossary_manager.protect_glossary_terms(
                protected_text, req.glossary
            )
            glossary_applied = len(glossary_protected) > 0

        # 7. Execute routed provider inference
        prov_req = TranslationRequest(
            text=protected_text,
            source_lang=src,
            target_lang=tgt,
            domain=req.domain,
            intent=Intent(req.intent.value),
            context=req.context,
            glossary=req.glossary,
            tenant_private_only=req.tenant_private_only,
            session_id=req.session_id,
            speaker_id=req.speaker_id,
            segment_id=req.segment_id,
        )

        prov_result = await self.router.route_and_translate(prov_req)

        # 8. Finalize translation: restore placeholders and run integrity checks
        final_text, final_flags = finalize_translation(
            source_text=normalized_source,
            raw_translated=prov_result.text,
            source_lang=src,
            target_lang=tgt,
            span_protector=span_protector,
            glossary_protected=glossary_protected,
            tech_protected=tech_protected,
            existing_flags=prov_result.quality_flags,
        )

        total_latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        res = TranslationResponseSchema(
            session_id=req.session_id,
            conversation_id=req.conversation_id,
            speaker_id=req.speaker_id,
            utterance_id=req.utterance_id,
            segment_id=req.segment_id,
            source_lang=src,
            target_lang=tgt,
            text=final_text,
            is_final=True,
            provider=prov_result.provider,
            model=prov_result.model,
            latency_ms=total_latency_ms,
            confidence=prov_result.confidence,
            quality_flags=final_flags,
            tm_match=None,
            glossary_applied=glossary_applied,
            pivoted=prov_result.pivoted,
        )

        # Store in cache
        if req.segment_id:
            translation_cache.put(req.segment_id, tgt, res)

        return res


translation_engine = TranslationEngine()

