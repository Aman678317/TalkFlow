"""Health / readiness / version / metrics (PDD §63, §64).

/health  = process alive (no dependency checks)
/ready   = ALL required dependencies ready; 503 otherwise
/version = build info
/metrics = Prometheus
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Request

from app.config import settings

router = APIRouter()

START_TIME = time.time()


@router.get("/health")
@router.get("/healthz")
@router.get("/api/v1/health")
async def health():
    return {"status": "ok", "version": settings.version,
            "uptime_s": round(time.time() - START_TIME, 1)}


@router.get("/ready")
@router.get("/readyz")
@router.get("/api/v1/ready")
async def ready():
    from app.cache import cache
    from app.db.session import healthcheck as db_health
    from app.queue import queue
    from app.storage import storage

    checks = {
        "database": await db_health(),
        "cache": await cache().ping(),
        "queue": await queue().ping(),
        "storage": await storage().ping(),
    }
    if settings.livekit_enabled:
        from app.realtime import livekit_bridge
        checks["livekit_configured"] = livekit_bridge.enabled()

    ok = all(checks.values())
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"ready": ok, "checks": checks})


@router.get("/diagnostics/realtime")
@router.get("/api/v1/diagnostics/realtime")
async def realtime_diagnostics(request: Request):
    """Operational readiness snapshot; never performs inference or logs speech.

    Production requires the existing METRICS_TOKEN. Without a token configured,
    the endpoint is hidden rather than accidentally publishing deployment detail.
    """
    if settings.is_production:
        expected = settings.metrics_token
        if not expected:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Realtime diagnostics are disabled.")
        import secrets
        auth = request.headers.get("Authorization", "")
        supplied = (
            auth.removeprefix("Bearer ").strip()
            if auth.startswith("Bearer ")
            else request.headers.get("X-Metrics-Token", "")
        )
        if not secrets.compare_digest(supplied, expected):
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Unauthorized diagnostics access.")

    from app.realtime.diagnostics import build_realtime_readiness
    return build_realtime_readiness()


@router.get("/version")
async def version():
    return {
        "name": settings.app_name,
        "version": settings.version,
        "env": settings.app_env,
        "protocol_version": 1,
        "ai": _ai_info(),
    }


def _ai_info() -> dict:
    from app.ai import ai
    from gt_ai.types import Task
    out = {}
    for task in Task:
        out[task.value] = ai._configured_name(task)
    return out


@router.get("/metrics")
async def metrics(request: Request):
    if not settings.metrics_enabled:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Metrics endpoint is disabled.")
    if settings.is_production and settings.metrics_token:
        import secrets
        auth = request.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else request.headers.get("X-Metrics-Token", "")
        if not secrets.compare_digest(token, settings.metrics_token):
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Unauthorized metrics access.")
    from app.metrics import metrics_response
    return metrics_response()
