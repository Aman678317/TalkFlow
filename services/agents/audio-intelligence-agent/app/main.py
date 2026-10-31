"""Main FastAPI application entry point for TalkFlow Audio Intelligence Agent."""
from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.routes import router as api_router
from app.api.websocket import ws_router
from app.core.config import settings
from app.core.exceptions import AudioIntelligenceError, AudioValidationError, SessionCapacityExceededError
from app.core.logging import get_logger, setup_logging

# Configure logging at application import
setup_logging(
    level=settings.monitoring.log_level,
    structured=settings.monitoring.structured_logging,
)
log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    log.info(f"Starting {settings.agent.name} v{settings.agent.version}")
    log.info(f"Canonical audio: PCM16 mono {settings.audio.sample_rate}Hz / {settings.audio.frame_duration_ms}ms frames")
    log.info(f"Active VAD Provider: {settings.vad.provider.upper()} (Threshold: {settings.vad.speech_threshold})")
    log.info(f"Noise Suppression: {settings.noise_suppression.provider.upper()} (Enabled: {settings.noise_suppression.enabled})")
    log.info(f"OpenAI Agents SDK Brain: {settings.llm_agent.provider.upper()} ({settings.llm_agent.model})")
    yield
    # --- Shutdown ---
    log.info(f"Shutting down {settings.agent.name}...")


app = FastAPI(
    title="TalkFlow Audio Intelligence Agent",
    description="Agent 01 in the TalkFlow multilingual speech translation architecture.",
    version=settings.agent.version,
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception Handlers
@app.exception_handler(AudioValidationError)
async def audio_validation_exception_handler(request: Request, exc: AudioValidationError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "AudioValidationError", "message": exc.message, "details": exc.details},
    )


@app.exception_handler(SessionCapacityExceededError)
async def session_capacity_exception_handler(request: Request, exc: SessionCapacityExceededError):
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"error": "SessionCapacityExceededError", "message": exc.message},
    )


@app.exception_handler(AudioIntelligenceError)
async def general_audio_intelligence_exception_handler(request: Request, exc: AudioIntelligenceError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": exc.__class__.__name__, "message": exc.message, "details": exc.details},
    )


# Mount routers
app.include_router(api_router)
app.include_router(ws_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.api.host,
        port=settings.api.port,
        reload=settings.api.debug,
    )

