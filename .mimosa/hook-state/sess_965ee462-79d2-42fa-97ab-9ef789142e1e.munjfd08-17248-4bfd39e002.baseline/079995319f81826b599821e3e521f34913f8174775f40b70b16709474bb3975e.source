"""Health, readiness, version, component health, audio health, metrics (sections 63/64/80/110)."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from ai.bootstrap import get_router
from globaltalk.core.cache import cache_backend_name, get_cache
from globaltalk.core.config import settings
from globaltalk.core.db import get_db
from globaltalk.core.metrics import metrics

router = APIRouter(tags=["health"])

VERSION = "0.1.0"
BUILD_DATE = "2026-09-26"


@router.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@router.get("/version")
def version():
    return {"name": "globaltalk-api", "version": VERSION, "build_date": BUILD_DATE,
            "env": settings.app_env, "protocol_version": 1}


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    """READY only when required dependencies answer. Optional components degrade, not fail."""
    checks: dict[str, dict] = {}
    ok = True

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok", "backend": "sqlite" if settings.is_sqlite
                              else "postgresql"}
    except Exception as exc:
        checks["database"] = {"status": "failed", "error": str(exc)[:200]}
        ok = False

    backend = cache_backend_name()
    try:
        get_cache().set("__ready_probe__", "1", ttl=5)
        checks["cache"] = {"status": "ok", "backend": backend}
    except Exception as exc:
        checks["cache"] = {"status": "degraded", "backend": backend,
                           "error": str(exc)[:200]}  # memory fallback keeps us ready

    try:
        from globaltalk.core.storage import get_storage
        checks["storage"] = {"status": "ok" if get_storage().healthy() else "failed",
                             "backend": get_storage().name}
        if checks["storage"]["status"] == "failed":
            ok = False
    except Exception as exc:
        checks["storage"] = {"status": "failed", "error": str(exc)[:200]}
        ok = False

    if settings.livekit_configured:
        from services.realtime.livekit_adapter import adapter
        st = adapter.health()
        checks["livekit"] = {"status": "ok" if st.healthy else "failed", "reason": st.reason}
        if not st.healthy:
            ok = False  # configured but broken → not ready (misconfiguration must surface)
    else:
        checks["livekit"] = {"status": "not_configured",
                             "note": "WebSocket audio transport active"}

    return Response(
        status_code=200 if ok else 503,
        media_type="application/json",
        content='{"status": "%s", "checks": %s}' % (
            "ready" if ok else "not_ready",
            __import__("json").dumps(checks, default=str)))


@router.get("/internal/components")
def components():
    """Open-source component health system (section 80)."""
    router_ai = get_router()
    out = []

    def comp(name, task, provider_name, *, optional=True, license_status="REVIEWED",
             gpu_required=False, version=""):
        healthy = router_ai.health(task, provider_name) if provider_name else False
        status = "READY" if healthy else ("OPTIONAL" if optional else "FAILED")
        out.append({"component": name, "task": task, "provider": provider_name,
                    "version": version, "status": status, "health": "ok" if healthy else "down",
                    "license_review_status": license_status, "gpu_required": gpu_required,
                    "loaded_model": healthy, "latency": None,
                    "last_check": datetime.now(timezone.utc).isoformat()})

    comp("faster-whisper", "stt", "faster-whisper", optional=False,
         license_status="MIT — REVIEWED", version=settings.stt_model)
    comp("argos-translate", "mt", "argos", optional=False,
         license_status="MIT — REVIEWED (per-package model licenses vary)")
    comp("passthrough-fallback", "mt", "passthrough", optional=False,
         license_status="N/A (internal)")
    comp("kokoro-tts", "tts", "kokoro", license_status="Apache-2.0 — REVIEWED")
    comp("langid", "langid", "langid", license_status="MIT — REVIEWED")
    comp("script-heuristic-langid", "langid", "script-heuristic", license_status="Internal")
    comp("vad", "vad", settings.vad_provider, license_status="MIT — REVIEWED (silero)")
    comp("vllm", "llm", "vllm", license_status="Apache-2.0 — REVIEWED")
    comp("extractive-assistant", "llm", "extractive", license_status="Internal")
    comp("embeddings", "embedding", "hash", license_status="Internal")

    # LiveKit
    if settings.livekit_configured:
        from services.realtime.livekit_adapter import adapter
        st = adapter.health()
        out.append({"component": "livekit", "task": "realtime-media",
                    "provider": "livekit-server", "version": st.version,
                    "status": "READY" if st.healthy else "FAILED",
                    "health": st.reason, "license_review_status": "Apache-2.0 — REVIEWED",
                    "gpu_required": False, "loaded_model": st.healthy, "latency": None,
                    "last_check": datetime.now(timezone.utc).isoformat()})
    else:
        out.append({"component": "livekit", "task": "realtime-media",
                    "provider": "livekit-server", "version": "",
                    "status": "NOT_CONFIGURED",
                    "health": "WebSocket PCM transport in use (dev)",
                    "license_review_status": "Apache-2.0 — REVIEWED", "gpu_required": False,
                    "loaded_model": False, "latency": None,
                    "last_check": datetime.now(timezone.utc).isoformat()})

    # Docling (optional parser upgrade)
    docling = False
    try:
        import docling  # noqa: F401
        docling = True
    except ImportError:
        pass
    out.append({"component": "docling", "task": "document-parser", "provider": "docling",
                "version": "", "status": "READY" if docling else "OPTIONAL",
                "health": "installed" if docling else "built-in parsers active (pypdf/docx/pptx/openpyxl)",
                "license_review_status": "MIT — REVIEWED", "gpu_required": False,
                "loaded_model": docling, "latency": None,
                "last_check": datetime.now(timezone.utc).isoformat()})

    return {"components": out,
            "cache_backend": cache_backend_name(),
            "storage_backend": settings.storage_backend}


@router.get("/internal/audio-health")
def audio_health(db: Session = Depends(get_db)):
    """Section 110: realtime audio engine health."""
    from globaltalk.realtime.hub import hub
    router_ai = get_router()
    return {
        "vad": {"provider": settings.vad_provider,
                "status": "ok" if router_ai.health("vad", settings.vad_provider) else "down"},
        "stt": {"provider": "faster-whisper", "model": settings.stt_model,
                "status": "ok" if router_ai.health("stt", "faster-whisper") else "down"},
        "tts": {"provider": "kokoro",
                "status": "ok" if router_ai.health("tts", "kokoro") else "not_configured"},
        "diarization": {"status": "disabled (flag: speaker_diarization)"},
        "noise_suppression": {"status": "disabled (flag: audio_enhancement)"},
        "gpu": {"available": settings.stt_device == "cuda"},
        "queue_depth": None,
        "active_meetings": hub.active_meetings(),
        "active_participants": hub.active_participants(),
        "latency_mode_default": settings.realtime_latency_mode,
        "sample_rate": settings.audio_sample_rate,
    }


@router.get("/metrics")
def prometheus_metrics():
    return Response(content=metrics.render(), media_type="text/plain; version=0.0.4")
