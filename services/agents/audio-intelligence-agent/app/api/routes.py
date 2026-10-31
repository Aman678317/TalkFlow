"""REST endpoints for Audio Intelligence Agent."""
from __future__ import annotations

import time
from typing import Any, Dict
from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import HTMLResponse
from app.core.config import settings
from app.models.schemas import AgentInfoResponse, AudioProcessResponse
from app.monitoring.metrics import metrics
from app.providers.noise_suppression import get_noise_suppressor
from app.providers.vad import get_vad_provider
from app.services.audio_processor import audio_processor
from app.ui.dashboard import DASHBOARD_HTML, FAVICON_SVG

router = APIRouter()
START_TIME = time.time()


@router.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse, summary="Interactive Control Dashboard")
async def root_dashboard() -> HTMLResponse:
    """Serves the TalkFlow Audio Intelligence Agent Interactive Web Dashboard and Playground."""
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


@router.get("/ready", summary="Readiness and dependency checks")
async def readiness_check() -> Dict[str, Any]:
    """Validates operational readiness of VAD and noise suppression providers."""
    vad = get_vad_provider(settings.vad.provider, settings.vad.sensitivity)
    denoiser = get_noise_suppressor(settings.noise_suppression.provider, settings.noise_suppression.enabled)

    vad_ready = vad.is_available()
    denoiser_ready = denoiser.is_available()

    ready = vad_ready and denoiser_ready
    status_code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE

    payload = {
        "ready": ready,
        "vad": {
            "provider": vad.name,
            "available": vad_ready,
        },
        "noise_suppression": {
            "provider": denoiser.name,
            "available": denoiser_ready,
        },
        "active_sessions": audio_processor.session_manager.active_session_count,
    }

    if not ready:
        raise HTTPException(status_code=status_code, detail=payload)
    return payload


@router.get("/metrics", summary="Prometheus metrics")
async def get_metrics() -> Response:
    """Exports Prometheus-compatible metrics for monitoring and latency audits."""
    data, content_type = metrics.export_metrics()
    return Response(content=data, media_type=content_type)


@router.get("/api/v1/agent/info", response_model=AgentInfoResponse, summary="Agent metadata and capabilities")
async def get_agent_info() -> AgentInfoResponse:
    """Returns agent identity, version, audio format contracts, and active session count."""
    return AgentInfoResponse(
        name=settings.agent.name,
        version=settings.agent.version,
        description=settings.agent.description,
        canonical_format={
            "sample_rate": settings.audio.sample_rate,
            "channels": settings.audio.channels,
            "encoding": settings.audio.encoding,
            "frame_duration_ms": settings.audio.frame_duration_ms,
        },
        supported_formats=["pcm_s16le", "wav"],
        vad_provider=settings.vad.provider,
        noise_suppression_provider=settings.noise_suppression.provider,
        llm_agent_enabled=settings.llm_agent.enabled,
        llm_model=settings.llm_agent.model if settings.llm_agent.enabled else None,
        active_sessions=audio_processor.session_manager.active_session_count,
        uptime_seconds=round(time.time() - START_TIME, 2),
    )


@router.post(
    "/api/v1/audio/process",
    response_model=AudioProcessResponse,
    summary="Process complete audio file",
)
async def process_audio_file_endpoint(
    file: UploadFile = File(...),
    session_id: str = Form(None),
    conversation_id: str = Form(None),
    speaker_id: str = Form("user_001"),
) -> AudioProcessResponse:
    """Receives a complete audio file (WAV or PCM), normalizes it, runs 50ms streaming pipeline,
    and returns segmented, timestamped chunks with quality diagnostics.
    """
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        response = await audio_processor.process_audio_file(
            file_bytes=content,
            filename=file.filename or "audio.wav",
            session_id=session_id,
            conversation_id=conversation_id,
            speaker_id=speaker_id,
        )
        return response
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Audio processing failed: {str(exc)}")


@router.post("/api/v1/audio/brain/diagnostic", summary="Run Audio Intelligence operational diagnostic")
async def audio_brain_diagnostic(query: str = "Assess acoustic environment") -> Dict[str, Any]:
    """Queries Audio Intelligence Agent operational diagnostic out-of-band."""
    return {
        "brain_active": settings.llm_agent.enabled,
        "model": settings.llm_agent.model,
        "base_url": settings.llm_agent.base_url,
        "query": query,
        "answer": f"Audio Intelligence Agent (Agent 01) active. VAD Engine: {settings.vad.provider}, Noise Suppression: {settings.noise_suppression.provider}, LLM Acoustic Advisor: {settings.llm_agent.model} via Ollama.",
    }


