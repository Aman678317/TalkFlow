"""Main FastAPI application entrypoint for Agent 07 Audio Delivery Agent."""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from app.api.routes import router
from app.api.websocket import ws_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.monitoring.metrics import metrics
from app.ui.dashboard import DASHBOARD_HTML

setup_logging()
logger = get_logger("main")
settings = get_settings()
START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Starting TalkFlow Audio Synchronization & Delivery Agent (Agent 07)",
        extra={"port": settings.server.port, "host": settings.server.host}
    )
    yield
    logger.info("Shutting down TalkFlow Audio Synchronization & Delivery Agent")


app = FastAPI(
    title="TalkFlow Audio Synchronization & Delivery Agent (Agent 07)",
    description="Final audio delivery component of TalkFlow AI multilingual pipeline. "
                "Handles jitter buffering, conversational sync, 1-to-N fanout, and TalkFlow 0x54 wire framing.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(router, prefix="/api/v1")
app.include_router(ws_router)


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Serve interactive web dashboard."""
    return HTMLResponse(content=DASHBOARD_HTML)


@app.get("/pipeline", response_class=HTMLResponse)
async def get_pipeline_dashboard():
    """Serve unified 7-agent pipeline dashboard."""
    pipeline_file = Path(__file__).resolve().parent.parent.parent / "pipeline_dashboard.html"
    if pipeline_file.exists():
        with open(pipeline_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content=DASHBOARD_HTML)


@app.get("/api/v1/sample-audio/big")
async def get_sample_big_audio():
    """Serve sample 10-second human speech WAV for end-to-end demonstrations."""
    from fastapi import HTTPException, Response
    fixture_path = Path(__file__).resolve().parent.parent.parent / "audio-intelligence-agent" / "tests" / "fixtures" / "en_example.wav"
    if not fixture_path.exists():
        raise HTTPException(status_code=404, detail="Sample audio fixture not found")
    with open(fixture_path, "rb") as f:
        data = f.read()
    return Response(content=data, media_type="audio/wav")


@app.get("/api/v1/sample-audio/5min")
async def get_sample_5min_audio():
    """Serve complete 5-minute (300-second) natural Hindi speech WAV for full-length validation."""
    from fastapi import HTTPException, Response
    fixture_path = Path(__file__).resolve().parent.parent.parent / "storage" / "hindi_5min_speech.wav"
    if not fixture_path.exists():
        raise HTTPException(status_code=404, detail="5-minute audio fixture not found")
    with open(fixture_path, "rb") as f:
        data = f.read()
    return Response(
        content=data,
        media_type="audio/wav",
        headers={"Content-Disposition": "attachment; filename=hindi_5min_speech.wav"}
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    uptime_sec = time.time() - START_TIME
    return {
        "status": "healthy",
        "agent": "Agent 07: Audio Synchronization & Delivery",
        "service": "audio-delivery-agent",
        "version": "1.0.0",
        "port": settings.server.port,
        "uptime_seconds": round(uptime_sec, 2),
    }


@app.get("/metrics", response_class=PlainTextResponse)
async def get_prometheus_metrics():
    """Prometheus exposition metrics endpoint."""
    return PlainTextResponse(metrics.generate_prometheus_text(), media_type="text/plain")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=settings.server.port, reload=False)

