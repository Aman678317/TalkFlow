"""REST endpoints for TalkFlow Speech Recognition Agent (Agent 02)."""
from __future__ import annotations

import time
from typing import Any, Dict, List
from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import HTMLResponse

from app.agents.brain import stt_brain

from app.core.config import settings
from app.models.events import InboundAudioSegmentEvent
from app.models.schemas import AgentInfoResponse, LanguageCapability, TranscribeResponse
from app.monitoring.metrics import metrics
from app.providers import get_stt_provider
from app.services.transcription_service import transcription_service
from app.stt.language_hints import LanguageRegistry
from app.ui.dashboard import DASHBOARD_HTML, FAVICON_SVG

router = APIRouter()
START_TIME = time.time()


@router.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse, summary="Interactive Control Dashboard")
async def root_dashboard() -> HTMLResponse:
    """Serves the TalkFlow Speech Recognition Agent Interactive Web Dashboard and Playground."""
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
    """Validates operational readiness of STT provider without triggering heavy model load."""
    provider = get_stt_provider()
    is_avail = provider.is_available()

    payload = {
        "ready": is_avail,
        "provider": provider.name,
        "model": provider.model_name,
        "active_sessions": transcription_service.session_manager.active_session_count,
    }
    if not is_avail:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=payload)
    return payload


@router.get("/metrics", summary="Prometheus metrics")
async def get_metrics() -> Response:
    """Exports Prometheus-compatible metrics for monitoring and latency audits."""
    data, content_type = metrics.export_metrics()
    return Response(content=data, media_type=content_type)


@router.get("/api/v1/agent/info", response_model=AgentInfoResponse, summary="Agent metadata and capabilities")
async def get_agent_info() -> AgentInfoResponse:
    """Returns agent identity, version, model, supported capabilities, and active session count."""
    provider = get_stt_provider()
    return AgentInfoResponse(
        name=settings.agent.name,
        version=settings.agent.version,
        description="TalkFlow Speech Recognition Agent (Agent 02) for real-time multilingual STT and streaming captions",
        provider=provider.name,
        model=provider.model_name,
        device=settings.stt.device,
        compute_type=settings.stt.compute_type,
        canonical_format={
            "sample_rate": settings.audio.canonical_sample_rate,
            "channels": settings.audio.channels,
            "encoding": settings.audio.encoding,
            "frame_duration_ms": settings.audio.frame_duration_ms,
        },
        supported_languages_count=len(provider.supported_languages()),
        streaming_supported=True,
        agent_brain_enabled=settings.llm_agent.enabled,
        agent_brain_model=settings.llm_agent.model if settings.llm_agent.enabled else None,
        active_sessions=transcription_service.session_manager.active_session_count,
        uptime_seconds=round(time.time() - START_TIME, 2),
    )


@router.get("/api/v1/stt/providers", summary="List available providers")
async def list_providers() -> List[Dict[str, Any]]:
    """Returns available STT provider adapters and their runtime readiness."""
    provider = get_stt_provider()
    return [
        {
            "name": provider.name,
            "model": provider.model_name,
            "device": settings.stt.device,
            "compute_type": settings.stt.compute_type,
            "available": provider.is_available(),
        }
    ]


@router.get("/api/v1/stt/languages", response_model=List[LanguageCapability], summary="List supported languages")
async def list_languages() -> List[LanguageCapability]:
    """Returns list of supported Indian and international languages with code-switching status."""
    return LanguageRegistry.get_capabilities()


@router.post("/api/v1/stt/transcribe", response_model=TranscribeResponse, summary="Transcribe complete audio file")
async def transcribe_file_endpoint(
    file: UploadFile = File(...),
    session_id: str = Form(None),
    conversation_id: str = Form(None),
    speaker_id: str = Form("user_001"),
    language_hint: str = Form(None),
) -> TranscribeResponse:
    """Transcribes an uploaded audio file (WAV or PCM) and returns full text with word-level timestamps."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded audio file is empty")

    if len(content) > settings.audio.max_file_size_bytes:
        max_mb = settings.audio.max_file_size_bytes / (1024 * 1024)
        file_mb = len(content) / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"Audio file size ({file_mb:.1f} MB) exceeds maximum allowed limit ({max_mb:.0f} MB)",
        )

    resp = await transcription_service.transcribe_audio_file(
        file_bytes=content,
        filename=file.filename or "audio.wav",
        session_id=session_id,
        conversation_id=conversation_id,
        speaker_id=speaker_id,
        language_hint=language_hint,
    )
    return resp


@router.post("/api/v1/stt/segment", response_model=TranscribeResponse, summary="Transcribe Agent 01 segment")
async def transcribe_segment_endpoint(
    event: InboundAudioSegmentEvent,
) -> TranscribeResponse:
    """Receives a clean finalized segment from Agent 01 and returns its transcription."""
    from app.integration.agent01_adapter import Agent01Adapter

    pcm16, meta = Agent01Adapter.extract_pcm16_and_meta(event)

    return await transcription_service.transcribe_agent01_segment(
        pcm16_bytes=pcm16,
        session_id=meta["session_id"],
        conversation_id=meta["conversation_id"],
        speaker_id=meta["speaker_id"],
        utterance_id=meta["utterance_id"],
        segment_id=meta["segment_id"],
        seq=meta["seq"],
        start_ms=meta["start_ms"],
        sample_rate=meta["sample_rate"],
    )


@router.post("/api/v1/stt/brain/diagnostic", summary="Run STT operational reasoning query")
async def stt_brain_diagnostic(query: str = Query("Check STT operational health", description="Diagnostic question")) -> Dict[str, Any]:
    """Queries the Speech Recognition Operations Brain (Ollama/Qwen) out-of-band."""
    answer = await stt_brain.run_diagnostics(query)
    return {
        "brain_active": stt_brain.enabled,
        "model": stt_brain.model_name,
        "answer": answer,
    }


@router.get("/api/v1/sample-audio/dhun", summary="Serve user dhun MP3 sample")
async def get_dhun_sample():
    """Serves the user's uploaded dhun audio sample."""
    from fastapi.responses import FileResponse
    import os
    path = r"I:\vioces agent\kalsstockmedia-free-soul-shri-ram-jai-ram-jai-jai-ram-dhun-385110.mp3"
    if not os.path.exists(path):
        path = r"I:\kalsstockmedia-free-soul-shri-ram-jai-ram-jai-jai-ram-dhun-385110.mp3"
    return FileResponse(path, media_type="audio/mpeg", filename="kalsstockmedia-free-soul-shri-ram-jai-ram-jai-jai-ram-dhun-385110.mp3")


