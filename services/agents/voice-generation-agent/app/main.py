"""Main Application Entrypoint for TalkFlow Agent 06 (Voice Generation Agent)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as tts_router
from app.api.websocket import ws_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.monitoring.metrics import metrics
from app.ui.dashboard import get_dashboard_html

setup_logging()
logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown hooks."""
    settings = get_settings()
    logger.info(
        "TalkFlow Voice Generation Agent (Agent 06) starting up...",
        extra={
            "service": "talkflow-voice-generation-agent",
            "port": settings.server_port,
            "offline_only": settings.offline_only,
            "private_only": settings.private_only,
            "default_provider": settings.default_provider,
        },
    )
    yield
    logger.info("TalkFlow Voice Generation Agent shutting down...")


settings = get_settings()

app = FastAPI(
    title="TalkFlow Voice Generation Agent (TTS)",
    version="1.0.0",
    description="Agent 06 in TalkFlow real-time multilingual pipeline. Converts approved translations to synthetic speech for Agent 07.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(tts_router)
app.include_router(ws_router)


@app.get("/health", tags=["Health"])
async def health():
    """Top-level health check endpoint."""
    return {
        "status": "healthy",
        "agent": "voice_generation_agent",
        "agent_id": "agent-06",
        "service": "talkflow-voice-generation-agent",
        "port": 8006,
    }


@app.get("/", tags=["Dashboard"])
async def dashboard():
    """Interactive Web UI Dashboard for Agent 06."""
    return get_dashboard_html()


@app.get("/metrics", tags=["Monitoring"])
async def prometheus_metrics():
    """Expose Prometheus formatted telemetry metrics."""
    return Response(content=metrics.to_prometheus(), media_type="text/plain; version=0.0.4")

