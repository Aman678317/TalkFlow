"""Health / readiness / version / metrics (PDD §63, §64).

/health  = process alive (no dependency checks)
/ready   = ALL required dependencies ready; 503 otherwise
/version = build info
/metrics = Prometheus
"""
from __future__ import annotations

import time

from fastapi import APIRouter

from app.config import settings

router = APIRouter()

START_TIME = time.time()


@router.get("/health")
async def health():
    return {"status": "ok", "version": settings.version,
            "uptime_s": round(time.time() - START_TIME, 1)}


@router.get("/ready")
async def ready():
    from app.cache import cache
    from app.db.session import healthcheck as db_health
    from app.storage import storage

    checks = {
        "database": await db_health(),
        "cache": await cache().ping(),
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
async def metrics():
    from app.metrics import metrics_response
    return metrics_response()
