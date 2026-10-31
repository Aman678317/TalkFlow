"""Multi-target translation fan-out with distinct-target deduplication and bounded concurrency."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List, Set
from app.models.schemas import BatchTargetResult, BatchTranslationRequestSchema, BatchTranslationResponseSchema, TranslationRequestSchema
from app.services.idempotency import idempotency_coordinator
from app.translation.engine import translation_engine

log = logging.getLogger("agent04.services.fanout")


class TranslationFanoutCoordinator:
    """Dispatches independent concurrent translation jobs across distinct requested target languages."""

    def __init__(self, max_concurrency: int = 8) -> None:
        self.semaphore = asyncio.Semaphore(max_concurrency)

    async def execute_fanout(self, batch_req: BatchTranslationRequestSchema) -> BatchTranslationResponseSchema:
        start_time = time.perf_counter()
        # Invariant 1: Deduplicate target languages so N listeners requesting English = 1 MT job
        distinct_targets = list(dict.fromkeys(t.lower().strip() for t in batch_req.target_langs if t.strip()))
        results: Dict[str, BatchTargetResult] = {}

        async def _translate_target(tgt: str) -> None:
            async with self.semaphore:
                target_start = time.perf_counter()
                segment_id = batch_req.segment_id or "unassigned_segment"

                # Check in-flight idempotency
                fut, is_creator = await idempotency_coordinator.get_or_create_job(segment_id, tgt)
                if not is_creator and fut:
                    try:
                        res = await fut
                        results[tgt] = res
                        return
                    except Exception as e:
                        log.warning(f"Reused in-flight job for {tgt} failed: {e}")

                req = TranslationRequestSchema(
                    text=batch_req.text,
                    source_lang=batch_req.source_lang,
                    target_lang=tgt,
                    session_id=batch_req.session_id,
                    conversation_id=batch_req.conversation_id,
                    speaker_id=batch_req.speaker_id,
                    utterance_id=batch_req.utterance_id,
                    segment_id=batch_req.segment_id,
                    domain=batch_req.domain,
                    intent=batch_req.intent,
                    context=batch_req.context,
                    glossary=batch_req.glossary,
                    tenant_private_only=batch_req.tenant_private_only,
                    formality=batch_req.formality,
                )

                try:
                    res = await translation_engine.translate_single(req)
                    target_latency = round((time.perf_counter() - target_start) * 1000.0, 2)
                    target_result = BatchTargetResult(
                        target_lang=tgt,
                        text=res.text,
                        status="identity" if res.source_equals_target else "success",
                        provider=res.provider,
                        model=res.model,
                        latency_ms=target_latency,
                        quality_flags=res.quality_flags,
                        pivoted=res.pivoted,
                    )
                    results[tgt] = target_result
                    await idempotency_coordinator.complete_job(segment_id, tgt, target_result)
                except Exception as exc:
                    # Invariant 2: Per-target error isolation — one failed target never blocks other targets
                    log.error(f"Target language '{tgt}' translation failed: {exc}")
                    target_latency = round((time.perf_counter() - target_start) * 1000.0, 2)
                    fail_result = BatchTargetResult(
                        target_lang=tgt,
                        text="",
                        status="failed",
                        provider="unknown",
                        model="unknown",
                        latency_ms=target_latency,
                        quality_flags=["provider_failure"],
                        error_message=str(exc),
                    )
                    results[tgt] = fail_result
                    await idempotency_coordinator.complete_job(segment_id, tgt, fail_result, error=exc)

        # Execute all targets concurrently
        await asyncio.gather(*[_translate_target(tgt) for tgt in distinct_targets])

        total_latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        return BatchTranslationResponseSchema(
            session_id=batch_req.session_id,
            conversation_id=batch_req.conversation_id,
            speaker_id=batch_req.speaker_id,
            utterance_id=batch_req.utterance_id,
            segment_id=batch_req.segment_id,
            source_lang=batch_req.source_lang,
            source_text=batch_req.text,
            requested_targets_count=len(batch_req.target_langs),
            unique_translation_jobs_count=len(distinct_targets),
            results=results,
            total_latency_ms=total_latency_ms,
        )


fanout_coordinator = TranslationFanoutCoordinator()

