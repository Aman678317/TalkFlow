"""FastAPI REST routes for Neural Translation Agent (Agent 04)."""
from __future__ import annotations

import time
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from app.agents.brain import mt_operations_agent
from app.core.config import settings
from app.core.logging import get_logger
from app.models.events import Agent03TranscriptEvent, TranslationFinalEvent
from app.models.schemas import (
    AgentInfoResponse,
    BatchTranslationRequestSchema,
    BatchTranslationResponseSchema,
    LanguagePairInfo,
    TranslationRequestSchema,
    TranslationResponseSchema,
    ValidatePairRequestSchema,
    ValidatePairResponseSchema,
)
from app.monitoring.metrics import metrics
from app.routing.capability_registry import capability_registry
from app.routing.provider_router import provider_router
from app.services.session_manager import session_manager
from app.services.translation_service import translation_service
from app.ui.dashboard import DASHBOARD_HTML

START_TIME = time.time()
log = get_logger("api.routes")
router = APIRouter()


@router.get("/", response_class=HTMLResponse, summary="Agent 04 Web Dashboard")
async def get_dashboard() -> str:
    """Renders the dark-mode interactive MT testing dashboard."""
    return DASHBOARD_HTML


@router.get("/health", summary="Basic service health probe")
async def health_check() -> Dict[str, Any]:
    return {
        "status": "ok",
        "agent": settings.agent.name,
        "version": settings.agent.version,
        "timestamp": time.time(),
    }


@router.get("/ready", summary="Readiness check")
async def ready_check() -> Dict[str, Any]:
    return {
        "ready": True,
        "primary_provider": settings.translation.primary_provider,
        "providers_ready": [p["name"] for p in provider_router.list_providers() if p["ready"]],
    }


@router.get("/metrics", summary="Prometheus telemetry")
async def get_metrics() -> Response:
    data, content_type = metrics.export_metrics()
    return Response(content=data, media_type=content_type)


@router.get("/api/v1/agent/info", response_model=AgentInfoResponse, summary="Agent metadata and capabilities")
async def get_agent_info() -> AgentInfoResponse:
    caps = capability_registry.list_capabilities()
    active_provs = [p["name"] for p in provider_router.list_providers() if p["ready"]]
    return AgentInfoResponse(
        name=settings.agent.name,
        version=settings.agent.version,
        description="TalkFlow Neural Translation Agent (Agent 04) for zero-pivot multi-target translation and Hinglish code-switching",
        primary_provider=settings.translation.primary_provider,
        default_model=settings.translation.default_model,
        device=settings.translation.device,
        compute_type=settings.translation.compute_type,
        active_providers=active_provs,
        supported_pairs_count=len(caps),
        zero_pivot_enforced=not settings.routing.allow_pivot_translation,
        agent_brain_enabled=settings.llm_agent.enabled,
        agent_brain_model=settings.llm_agent.model if settings.llm_agent.enabled else None,
        active_sessions=session_manager.active_session_count,
        uptime_seconds=round(time.time() - START_TIME, 2),
    )


@router.get("/api/v1/translation/providers", summary="List configured translation providers")
async def list_providers() -> List[Dict[str, Any]]:
    return provider_router.list_providers()


@router.get("/api/v1/translation/language-pairs", response_model=List[LanguagePairInfo], summary="List evaluated language pairs")
async def list_language_pairs() -> List[LanguagePairInfo]:
    caps = capability_registry.list_capabilities()
    return [
        LanguagePairInfo(
            source_lang=c.source_lang,
            target_lang=c.target_lang,
            status=c.status,
            provider=c.preferred_provider,
            model=c.model,
            direct=c.direct,
        )
        for c in caps
    ]


@router.post("/api/v1/translation/translate", response_model=TranslationResponseSchema, summary="Translate single source to one target")
async def translate_single_endpoint(req: TranslationRequestSchema) -> TranslationResponseSchema:
    """Translates source text into a single target language."""
    try:
        return await translation_service.translate_single(req)
    except Exception as e:
        log.error(f"Translation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/v1/translation/batch", response_model=BatchTranslationResponseSchema, summary="Translate one source to multiple independent targets")
async def translate_batch_endpoint(req: BatchTranslationRequestSchema) -> BatchTranslationResponseSchema:
    """Translates one canonical source segment independently into multiple target languages."""
    try:
        return await translation_service.translate_batch(req)
    except Exception as e:
        log.error(f"Batch translation failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/v1/translation/validate", response_model=ValidatePairResponseSchema, summary="Validate language pair readiness")
async def validate_pair_endpoint(req: ValidatePairRequestSchema) -> ValidatePairResponseSchema:
    src = req.source_lang.lower()
    tgt = req.target_lang.lower()
    cap = capability_registry.get_pair_capability(src, tgt)
    if cap:
        return ValidatePairResponseSchema(
            source_lang=src,
            target_lang=tgt,
            supported=cap.status in ("PRODUCTION", "SUPPORTED"),
            status=cap.status,
            recommended_provider=cap.preferred_provider,
            recommended_model=cap.model,
            direct_translation_supported=cap.direct,
            pivot_required=not cap.direct,
            notes=cap.notes,
        )
    return ValidatePairResponseSchema(
        source_lang=src,
        target_lang=tgt,
        supported=False,
        status="UNSUPPORTED",
        direct_translation_supported=False,
        pivot_required=False,
        notes="Language pair has not been configured or evaluated.",
    )


@router.post("/api/v1/translation/agent03/transcript", response_model=List[TranslationFinalEvent], summary="Ingest Agent 03 transcript analysis event")
async def ingest_agent03_event(event: Agent03TranscriptEvent) -> List[TranslationFinalEvent]:
    """Receives canonical speech transcript and language metadata from Agent 03."""
    log.info(f"Ingested transcript from Agent 03: segment={event.segment_id} lang={event.primary_language} text='{event.original_text[:50]}'")
    return await translation_service.handle_agent03_event(event)


@router.post("/api/v1/translation/brain/diagnostic", summary="Run operational reasoning query")
async def translation_brain_diagnostic(query: str = Query("Check translation capabilities", description="Operational diagnostic question")) -> Dict[str, Any]:
    """Queries the Neural Translation Operations Brain (Ollama/Qwen) out-of-band."""
    answer = await mt_operations_agent.diagnose_issue(query)
    return {
        "brain_active": mt_operations_agent.enabled,
        "model": mt_operations_agent.model_name,
        "answer": answer,
    }


