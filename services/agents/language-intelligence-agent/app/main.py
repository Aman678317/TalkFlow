"""Main FastAPI application entrypoint for TalkFlow Language Intelligence Agent (Agent 03)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router as api_router
from app.api.websocket import ws_router
from app.core.config import settings
from app.core.exceptions import (
    DetectionError,
    LanguageIntelligenceError,
    ProviderUnavailable,
    SessionCapacityExceededError,
    TextValidationError,
)
from app.core.logging import get_logger, setup_logging
from app.providers import get_all_providers

# Initialize logging
setup_logging(level=settings.monitoring.log_level)
log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    log.info(f"Starting {settings.agent.name} v{settings.agent.version}")
    log.info(f"Primary Text LID: {settings.detection.primary_text_provider.upper()} (Fallback: {settings.detection.fallback_text_provider.upper()})")
    log.info(f"Code-Switching Detection: {settings.code_switch.enabled} (Hinglish: {settings.code_switch.hinglish_latin_detection})")
    log.info(f"Operational Reasoning Brain: {settings.llm_agent.provider.upper()} ({settings.llm_agent.model})")

    # Warm up providers
    providers = get_all_providers()
    log.info(f"Loaded {len(providers)} language detection providers successfully")
    yield
    # --- Shutdown ---
    log.info(f"Shutting down {settings.agent.name}...")


app = FastAPI(
    title="TalkFlow Language Intelligence Agent (Agent 03)",
    description="Agent 03 in the TalkFlow multilingual speech translation architecture.",
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
@app.exception_handler(TextValidationError)
async def text_validation_exception_handler(request: Request, exc: TextValidationError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "TextValidationError", "message": exc.message, "details": exc.details},
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


@app.exception_handler(DetectionError)
async def detection_exception_handler(request: Request, exc: DetectionError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "DetectionError", "message": exc.message, "details": exc.details},
    )


@app.exception_handler(LanguageIntelligenceError)
async def general_lang_exception_handler(request: Request, exc: LanguageIntelligenceError):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": exc.__class__.__name__, "message": exc.message, "details": exc.details},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    log.error(f"Unhandled server error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": exc.__class__.__name__, "message": str(exc)},
    )


# Attach Routers
app.include_router(api_router)
app.include_router(ws_router)

