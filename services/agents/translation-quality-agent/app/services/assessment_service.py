"""Core translation assessment service coordinating evaluations and handoffs."""
from __future__ import annotations

import asyncio
from typing import List, Optional
from app.integration.agent06_publisher import publisher_to_agent06
from app.models.quality_report import QualityReport
from app.models.schemas import (
    BatchEvaluationRequestSchema,
    EvaluationRequestSchema,
    EvaluationResponseSchema,
    HumanReviewItem,
    PartialEvaluationRequestSchema,
    QualityDecision,
    ReferenceEvaluationRequestSchema,
)
from app.monitoring.metrics import metrics
from app.quality.report_builder import report_builder
from app.review.queue import review_queue
from app.services.idempotency import idempotency_cache


class AssessmentService:
    """Service facade for translation quality assessments, batching, and Agent 06 dispatch."""

    async def evaluate_single(
        self,
        request: EvaluationRequestSchema,
        reference: Optional[str] = None,
        retry_count: int = 0,
    ) -> EvaluationResponseSchema:
        """Evaluates a single translation candidate."""
        candidate_hash = QualityReport.compute_candidate_hash(
            request.source_text, request.target_text, request.source_lang, request.target_lang
        )

        # Check idempotency cache to avoid duplicate inference
        cached = idempotency_cache.get(candidate_hash)
        if cached is not None:
            return report_builder.to_response_schema(cached)

        # Execute evaluation pipeline
        report = report_builder.build_report(request, reference=reference, retry_count=retry_count)

        # Cache immutable report
        idempotency_cache.put(candidate_hash, report)

        # Record metrics
        metrics.record_evaluation(
            source_lang=report.source_lang,
            target_lang=report.target_lang,
            decision=report.decision.value,
            score=report.overall_score,
            latency_ms=report.evaluation_latency_ms,
            has_critical=report.has_critical_error,
        )

        # If HOLD_FOR_HUMAN, route to review queue
        if report.decision == QualityDecision.HOLD_FOR_HUMAN:
            review_queue.enqueue(
                HumanReviewItem(
                    evaluation_id=report.evaluation_id,
                    segment_id=report.segment_id,
                    source_text=report.source_text,
                    target_text=report.target_text,
                    source_lang=report.source_lang,
                    target_lang=report.target_lang,
                    suggested_decision=report.decision,
                    reasons=[i.description for i in report.issues],
                )
            )

        # Asynchronously dispatch accepted translation to Agent 06 (TTS)
        asyncio.create_task(publisher_to_agent06.dispatch_report(report))

        return report_builder.to_response_schema(report)

    async def evaluate_batch(
        self,
        request: BatchEvaluationRequestSchema,
    ) -> List[EvaluationResponseSchema]:
        """Evaluates a batch of translation candidates in bounded concurrency."""
        tasks = [self.evaluate_single(c) for c in request.candidates]
        return await asyncio.gather(*tasks)

    async def evaluate_partial(
        self,
        request: PartialEvaluationRequestSchema,
    ) -> EvaluationResponseSchema:
        """Lightweight check for provisional partial translations (<10ms)."""
        full_req = EvaluationRequestSchema(
            source_text=request.source_text,
            target_text=request.target_text,
            source_lang=request.source_lang,
            target_lang=request.target_lang,
            segment_id=request.segment_id or "partial_seg",
            mode="partial",
        )
        report = report_builder.build_report(full_req)
        return report_builder.to_response_schema(report)

    async def evaluate_reference(
        self,
        request: ReferenceEvaluationRequestSchema,
    ) -> EvaluationResponseSchema:
        """Evaluates translation candidate against trusted reference translation."""
        full_req = EvaluationRequestSchema(
            source_text=request.source_text,
            target_text=request.hypothesis_text,
            source_lang=request.source_lang,
            target_lang=request.target_lang,
            mode="reference",
        )
        return await self.evaluate_single(full_req, reference=request.reference_text)


assessment_service = AssessmentService()

