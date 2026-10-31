"""REST endpoints for TalkFlow Language Intelligence Agent (Agent 03)."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.agents.brain import agent_brain

from app.core.config import settings
from app.language.capabilities import TalkFlowCapabilityRegistry
from app.models.events import InboundTranscriptEvent, LanguageAnalysisFinalEvent
from app.models.schemas import AgentInfoResponse, DetectionResult, LanguageAnalysisResponse
from app.monitoring.metrics import metrics
from app.providers import get_all_providers, get_language_provider
from app.services.language_service import language_service
from app.ui.dashboard import DASHBOARD_HTML, FAVICON_SVG

router = APIRouter()
START_TIME = time.time()


class DetectRequest(BaseModel):
    text: str
    provider: Optional[str] = None
    language_hint: Optional[str] = None


class AnalyzeRequest(BaseModel):
    text: str
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    speaker_id: Optional[str] = "user_001"
    utterance_id: Optional[str] = None
    segment_id: Optional[str] = None
    seq: int = 1
    language_hint: Optional[str] = None
    stt_probability: Optional[float] = None


@router.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse, summary="Interactive Control Dashboard")
async def root_dashboard() -> HTMLResponse:
    """Serves the TalkFlow Language Intelligence Agent Interactive Web Dashboard."""
    return HTMLResponse(content=DASHBOARD_HTML)


@router.api_route("/favicon.ico", methods=["GET", "HEAD"], summary="Service Favicon")
async def get_favicon() -> Response:
    """Returns the SVG favicon for browser requests."""
    return Response(content=FAVICON_SVG, media_type="image/svg+xml")


@router.get("/health", summary="Basic health status")
async def health_check() -> Dict[str, Any]:
    """Returns basic service health status."""
    return {
        "status": "ok",
        "agent": settings.agent.name,
        "version": settings.agent.version,
        "timestamp": time.time(),
    }


@router.get("/ready", summary="Readiness probe")
async def readiness_check() -> Dict[str, Any]:
    """Validates operational readiness of language detection providers."""
    providers = get_all_providers()
    all_ready = any(p.healthy() for p in providers)

    payload = {
        "ready": all_ready,
        "providers": [
            {"name": p.name, "model": p.model_name, "healthy": p.healthy()}
            for p in providers
        ],
        "active_sessions": language_service.session_manager.active_session_count,
    }
    if not all_ready:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=payload)
    return payload


@router.get("/metrics", summary="Prometheus metrics")
async def get_metrics() -> Response:
    """Exports Prometheus-compatible metrics for monitoring and latency audits."""
    data, content_type = metrics.export_metrics()
    return Response(content=data, media_type=content_type)


@router.get("/api/v1/agent/info", response_model=AgentInfoResponse, summary="Agent metadata and capabilities")
async def get_agent_info() -> AgentInfoResponse:
    """Returns agent identity, version, models, and active session count."""
    providers = get_all_providers()
    return AgentInfoResponse(
        name=settings.agent.name,
        version=settings.agent.version,
        description="TalkFlow Language Intelligence Agent (Agent 03) for multi-signal LID and code-switching",
        primary_text_provider=settings.detection.primary_text_provider,
        fallback_text_provider=settings.detection.fallback_text_provider,
        code_switch_enabled=settings.code_switch.enabled,
        hinglish_detection_enabled=settings.code_switch.hinglish_latin_detection,
        supported_languages_count=len(TalkFlowCapabilityRegistry.list_all_capabilities()),
        active_sessions=language_service.session_manager.active_session_count,
        agent_brain_enabled=settings.llm_agent.enabled,
        agent_brain_model=settings.llm_agent.model if settings.llm_agent.enabled else None,
        uptime_seconds=round(time.time() - START_TIME, 2),
    )


@router.get("/api/v1/language/providers", summary="List available providers")
async def list_providers() -> List[Dict[str, Any]]:
    """Returns available language detection provider adapters and their readiness."""
    providers = get_all_providers()
    return [
        {
            "name": p.name,
            "model": p.model_name,
            "available": p.healthy(),
            "supported_languages_count": len(p.supported_languages()),
        }
        for p in providers
    ]


@router.get("/api/v1/language/capabilities", summary="List TalkFlow language capabilities")
async def list_capabilities() -> List[Dict[str, Any]]:
    """Returns list of evaluated Indian and international languages with translation tiers."""
    return TalkFlowCapabilityRegistry.list_all_capabilities()


@router.post("/api/v1/language/detect", response_model=DetectionResult, summary="Simple text language detection")
async def detect_language_endpoint(req: DetectRequest) -> DetectionResult:
    """Fast single-sentence statistical language identification without session state."""
    provider = get_language_provider(req.provider or settings.detection.primary_text_provider)
    return provider.detect(req.text, language_hint=req.language_hint)


@router.post("/api/v1/language/analyze", response_model=LanguageAnalysisResponse, summary="Full multi-signal analysis")
async def analyze_language_endpoint(req: AnalyzeRequest) -> LanguageAnalysisResponse:
    """Executes multi-signal evidence fusion, script analysis, and code-switching detection."""
    return await language_service.analyze_text(
        text=req.text,
        session_id=req.session_id,
        conversation_id=req.conversation_id,
        speaker_id=req.speaker_id or "user_001",
        utterance_id=req.utterance_id,
        segment_id=req.segment_id,
        seq=req.seq,
        language_hint=req.language_hint,
        stt_probability=req.stt_probability,
    )


@router.post("/api/v1/language/transcript", response_model=LanguageAnalysisFinalEvent, summary="Ingest Agent 02 transcript")
async def ingest_agent02_transcript(event: InboundTranscriptEvent) -> LanguageAnalysisFinalEvent:
    """Direct webhook/event bridge receiving transcript.final from Agent 02 and outputting Agent 04 event."""
    return await language_service.handle_agent02_transcript_event(event)


@router.post("/api/v1/language/brain/diagnostic", summary="Run Language Intelligence operational diagnostic")
async def language_brain_diagnostic(query: str = Query("Check language intelligence status", description="Diagnostic question")) -> Dict[str, Any]:
    """Queries Language Intelligence Agent operational diagnostic out-of-band."""
    diag = await agent_brain.diagnose_session_multilingualism("sess_diag", "user_001", [{"language": "hi"}, {"language": "en"}])
    return {
        "brain_active": agent_brain.enabled,
        "model": agent_brain.model,
        "query": query,
        "multilingual_analysis": diag,
    }

