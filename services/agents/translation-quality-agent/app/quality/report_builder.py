"""Quality report builder orchestrating all evaluation components."""
from __future__ import annotations

import time
import uuid
from typing import Optional
from app.checks.runner import integrity_runner
from app.evaluators.registry import evaluator_registry
from app.models.quality_report import QualityReport
from app.models.schemas import EvaluationRequestSchema, EvaluationResponseSchema
from app.quality.decision_engine import decision_engine
from app.quality.scorer import quality_scorer


class ReportBuilder:
    """Orchestrates deterministic checks, semantic evaluation, scoring, and report creation."""

    def build_report(
        self,
        request: EvaluationRequestSchema,
        reference: Optional[str] = None,
        retry_count: int = 0,
    ) -> QualityReport:
        t_start = time.perf_counter()

        eval_id = f"eval_{uuid.uuid4().hex[:12]}"
        candidate_hash = QualityReport.compute_candidate_hash(
            request.source_text, request.target_text, request.source_lang, request.target_lang
        )

        # 1. Deterministic Integrity Layer (<10ms)
        checks, issues, data_integrity_score, has_critical = integrity_runner.run_all(request)

        # 2. Semantic Quality Evaluation Layer (<20ms)
        if request.mode == "reference" and reference:
            ref_eval = evaluator_registry.get("sacrebleu")
            eval_res = ref_eval.evaluate(
                source=request.source_text,
                hypothesis=request.target_text,
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                reference=reference,
            ) if ref_eval else None
            semantic_score = eval_res.score if eval_res else 0.5
        else:
            sem_eval = evaluator_registry.get("semantic_multilingual")
            eval_res = sem_eval.evaluate(
                source=request.source_text,
                hypothesis=request.target_text,
                source_lang=request.source_lang,
                target_lang=request.target_lang,
            ) if sem_eval else None
            semantic_score = eval_res.score if eval_res else 0.85

        # 3. Multi-dimensional Scoring & Hard Gating
        overall_score, scores_dict = quality_scorer.calculate_scores(
            semantic_score=semantic_score,
            data_integrity_score=data_integrity_score,
            issues=issues,
            has_critical_error=has_critical,
        )

        # 4. Decision Engine
        decision, status, retry_rec = decision_engine.resolve_decision(
            overall_score=overall_score,
            issues=issues,
            has_critical_error=has_critical,
            current_retry_count=retry_count,
            current_provider=request.provider,
            source_lang=request.source_lang,
            target_lang=request.target_lang,
        )

        latency_ms = round((time.perf_counter() - t_start) * 1000, 2)

        return QualityReport(
            evaluation_id=eval_id,
            candidate_hash=candidate_hash,
            session_id=request.session_id,
            conversation_id=request.conversation_id,
            speaker_id=request.speaker_id,
            utterance_id=request.utterance_id,
            segment_id=request.segment_id,
            translation_id=request.translation_id,
            source_lang=request.source_lang,
            target_lang=request.target_lang,
            source_text=request.source_text,
            target_text=request.target_text,
            decision=decision,
            quality_status=status,
            overall_score=overall_score,
            semantic_score=scores_dict["semantic_accuracy"],
            data_integrity_score=scores_dict["data_integrity"],
            completeness_score=scores_dict["completeness"],
            terminology_score=scores_dict["terminology"],
            fluency_score=scores_dict["fluency"],
            checks=checks,
            issues=issues,
            has_critical_error=has_critical,
            provider=request.provider or "agent04",
            model=request.model or "unknown",
            evaluator_version="agent05-v1.0.0",
            evaluation_latency_ms=latency_ms,
            retry_recommendation=retry_rec,
        )

    def to_response_schema(self, report: QualityReport) -> EvaluationResponseSchema:
        checks_summary = {c.name: c.status for c in report.checks}
        return EvaluationResponseSchema(
            evaluation_id=report.evaluation_id,
            candidate_hash=report.candidate_hash,
            session_id=report.session_id,
            segment_id=report.segment_id,
            translation_id=report.translation_id,
            source_lang=report.source_lang,
            target_lang=report.target_lang,
            source_text=report.source_text,
            target_text=report.target_text,
            decision=report.decision,
            quality_status=report.quality_status,
            overall_score=report.overall_score,
            scores={
                "semantic": report.semantic_score,
                "data_integrity": report.data_integrity_score,
                "completeness": report.completeness_score,
                "terminology": report.terminology_score,
                "fluency": report.fluency_score,
            },
            issues=report.issues,
            checks=checks_summary,
            provider_provenance={"provider": report.provider, "model": report.model},
            retry_recommendation=report.retry_recommendation,
            evaluation_latency_ms=report.evaluation_latency_ms,
            timestamp=report.created_at,
        )


report_builder = ReportBuilder()

