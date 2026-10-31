"""Main FastAPI application entrypoint for TalkFlow Speech Recognition Agent (Agent 02)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router as api_router
from app.api.websocket import ws_router
from app.core.config import settings
from app.core.exceptions import (
    AudioValidationError,
    ProviderUnavailable,
    SessionCapacityExceededError,
    STTAgentError,
    TranscriptionError,
)
from app.core.logging import get_logger, setup_logging
from app.providers import get_stt_provider

# Setup logging
setup_logging(
    level=settings.monitoring.log_level,
    structured=settings.monitoring.structured_logging,
)
log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    log.info(f"Starting {settings.agent.name} v{settings.agent.version}")
    log.info(f"Canonical Audio: 16000Hz Mono PCM16 / 50ms frames")
    provider = get_stt_provider()
    log.info(f"Active STT Provider: {provider.name.upper()} (Model: {provider.model_name})")
    log.info(f"Inference Device: {settings.stt.device} (Compute: {settings.stt.compute_type}, Threads: {settings.stt.cpu_threads})")
    log.info(f"Anti-Hallucination Filter: {settings.anti_hallucination.enabled}")
    log.info(f"OpenAI Agents SDK Brain: {settings.llm_agent.provider.upper()} ({settings.llm_agent.model})")
    yield
    # --- Shutdown ---
    log.info(f"Shutting down {settings.agent.name}...")


app = FastAPI(
    title="TalkFlow Speech Recognition Agent (Agent 02)",
    description="Agent 02 in the TalkFlow multilingual speech translation architecture.",
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


@app.exception_handler(ProviderUnavailable)
async def provider_unavailable_exception_handler(request: Request, exc: ProviderUnavailable):
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"error": "ProviderUnavailable", "message": exc.message, "details": exc.details},
    )


@app.exception_handler(TranscriptionError)
async def transcription_exception_handler(request: Request, exc: TranscriptionError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "TranscriptionError", "message": exc.message, "details": exc.details},
    )


@app.exception_handler(STTAgentError)
async def general_stt_exception_handler(request: Request, exc: STTAgentError):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": exc.__class__.__name__, "message": exc.message, "details": exc.details},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    log.error(f"Unhandled server error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": exc.__class__.__name__, "message": str(exc)},
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
        reload=settings.agent.debug,
    )

