"""FastAPI REST routes and Agent 04 webhook handler for Translation Quality Agent."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse

from app.agents.brain import quality_brain
from app.core.config import settings
from app.core.logging import get_logger
from app.evaluators.registry import evaluator_registry
from app.integration.agent04_adapter import Agent04Adapter
from app.models.events import Agent04TranslationFinalEvent
from app.models.schemas import (
    AgentInfoResponse,
    BatchEvaluationRequestSchema,
    EvaluationRequestSchema,
    EvaluationResponseSchema,
    HumanReviewItem,
    HumanReviewSubmissionSchema,
    PartialEvaluationRequestSchema,
    ReferenceEvaluationRequestSchema,
)
from app.monitoring.metrics import metrics
from app.review.queue import review_queue
from app.services.assessment_service import assessment_service
from app.services.idempotency import idempotency_cache
from app.ui.dashboard import DASHBOARD_HTML

START_TIME = time.time()
log = get_logger("api.routes")
router = APIRouter()


@router.get("/", response_class=HTMLResponse, summary="Agent 05 Control Dashboard")
async def root_dashboard() -> HTMLResponse:
    """Interactive Translation Quality Control Dashboard and Testing Playground."""
    return HTMLResponse(content=DASHBOARD_HTML, status_code=200)


@router.get("/health", summary="Basic service health probe")
async def health_check() -> Dict[str, Any]:
    return {
        "status": "ok",
        "agent": settings.agent.name,
        "version": settings.agent.version,
        "timestamp": time.time(),
    }


@router.get("/ready", summary="Readiness probe")
async def readiness_check() -> Dict[str, Any]:
    return {
        "status": "ready",
        "primary_evaluator": settings.evaluation.reference_free_evaluator,
        "realtime_qa_enabled": settings.evaluation.realtime_qa_enabled,
        "final_qa_enabled": settings.evaluation.final_qa_enabled,
    }


@router.get("/metrics", summary="Prometheus telemetry metrics export")
async def get_metrics() -> Response:
    data, content_type = metrics.export_prometheus()
    return Response(content=data, media_type=content_type)


@router.get("/api/v1/agent/info", response_model=AgentInfoResponse, summary="Agent metadata and capabilities")
async def get_agent_info() -> AgentInfoResponse:
    return AgentInfoResponse(
        name=settings.agent.name,
        version=settings.agent.version,
        description="TalkFlow Translation Quality Agent (Agent 05) for autonomous data integrity and meaning preservation",
        primary_evaluator=settings.evaluation.reference_free_evaluator,
        active_evaluators=[e["name"] for e in evaluator_registry.list_available()],
        supported_metrics=["bleu", "chrf", "semantic_multilingual", "number_integrity", "currency_integrity", "negation_check"],
        decision_outcomes=["ACCEPT", "ACCEPT_WITH_WARNINGS", "RETRY_WITH_ALTERNATE_PROVIDER", "HOLD_FOR_HUMAN", "REJECT"],
        agent_brain_enabled=settings.llm_agent.enabled,
        agent_brain_model=settings.llm_agent.model if settings.llm_agent.enabled else None,
        pending_human_reviews=review_queue.pending_count,
        uptime_seconds=round(time.time() - START_TIME, 2),
    )


@router.post("/api/v1/quality/evaluate", response_model=EvaluationResponseSchema, summary="Evaluate single translation candidate")
async def evaluate_single(request: EvaluationRequestSchema) -> EvaluationResponseSchema:
    """Evaluates one final translation candidate against its canonical source."""
    return await assessment_service.evaluate_single(request)


@router.post("/api/v1/quality/evaluate/batch", response_model=List[EvaluationResponseSchema], summary="Batch evaluation")
async def evaluate_batch(request: BatchEvaluationRequestSchema) -> List[EvaluationResponseSchema]:
    """Evaluates multiple translation candidates concurrently."""
    return await assessment_service.evaluate_batch(request)


@router.post("/api/v1/quality/evaluate/partial", response_model=EvaluationResponseSchema, summary="Lightweight partial check")
async def evaluate_partial(request: PartialEvaluationRequestSchema) -> EvaluationResponseSchema:
    """Runs fast deterministic integrity checks (<10ms) on provisional streaming partials."""
    return await assessment_service.evaluate_partial(request)


@router.post("/api/v1/quality/evaluate/reference", response_model=EvaluationResponseSchema, summary="Offline reference evaluation")
async def evaluate_reference(request: ReferenceEvaluationRequestSchema) -> EvaluationResponseSchema:
    """Evaluates translation candidate against a trusted human reference translation (SacreBLEU / chrF++)."""
    return await assessment_service.evaluate_reference(request)


@router.get("/api/v1/quality/providers", summary="List available evaluation backends")
async def list_providers() -> List[Dict[str, str]]:
    return evaluator_registry.list_available()


@router.get("/api/v1/quality/languages", summary="List supported language pairs and quality status")
async def list_languages() -> List[Dict[str, Any]]:
    return [
        {"pair": "hi->en", "status": "SUPPORTED", "bleu_benchmark": 32.5, "chrf": 58.2},
        {"pair": "en->hi", "status": "SUPPORTED", "bleu_benchmark": 28.4, "chrf": 54.1},
        {"pair": "hi->mr", "status": "SUPPORTED", "bleu_benchmark": 26.8, "chrf": 51.5},
        {"pair": "en->mr", "status": "SUPPORTED", "bleu_benchmark": 24.1, "chrf": 48.9},
        {"pair": "en->ja", "status": "SUPPORTED", "bleu_benchmark": 29.8, "chrf": 52.3},
        {"pair": "en->bn", "status": "SUPPORTED", "bleu_benchmark": 27.2, "chrf": 50.1},
    ]


@router.get("/api/v1/quality/review-queue", response_model=List[HumanReviewItem], summary="Get human review queue")
async def get_review_queue(limit: int = Query(50, ge=1, le=200)) -> List[HumanReviewItem]:
    return review_queue.list_pending(limit=limit)


@router.post("/api/v1/quality/review", summary="Submit human reviewer feedback")
async def submit_review(submission: HumanReviewSubmissionSchema) -> Dict[str, Any]:
    item = review_queue.submit_review(submission)
    if not item:
        raise HTTPException(status_code=404, detail=f"Evaluation ID '{submission.evaluation_id}' not found in review queue.")
    return {"status": "success", "evaluation_id": submission.evaluation_id, "decision": submission.human_decision.value}


@router.post("/api/v1/quality/agent04/transcript", response_model=EvaluationResponseSchema, summary="Ingest Agent 04 translation event")
async def ingest_agent04_event(event: Agent04TranslationFinalEvent) -> EvaluationResponseSchema:
    """Webhook receiving translation.final directly from Agent 04."""
    req = Agent04Adapter.to_evaluation_request(event)
    resp = await assessment_service.evaluate_single(req)
    log.info(
        f"[Agent 04 -> Agent 05] Evaluated segment {event.segment_id} ({event.source_lang}->{event.target_lang}): "
        f"decision={resp.decision} score={resp.overall_score} in {resp.evaluation_latency_ms}ms"
    )
    return resp


@router.post("/api/v1/quality/brain/diagnostic", summary="Run operational reasoning query")
async def brain_diagnostic(query: str = Query(..., description="Operational diagnostic question")) -> Dict[str, Any]:
    """Queries the optional Translation Quality Operations Brain (Ollama/Qwen) out-of-band."""
    return await quality_brain.run_diagnostic(query)

