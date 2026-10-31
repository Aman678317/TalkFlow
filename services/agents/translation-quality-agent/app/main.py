"""FastAPI application entrypoint for TalkFlow Translation Quality Agent (Agent 05)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.api.websocket import ws_router
from app.core.config import settings
from app.core.exceptions import (
    DecisionPolicyError,
    EvaluatorUnavailableError,
    InvalidCandidateError,
    QualityAgentError,
)
from app.core.logging import get_logger, setup_logging

setup_logging()
log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info(f"Starting {settings.agent.name} v{settings.agent.version} on port {settings.api.port}")
    log.info(f"Primary reference-free evaluator: {settings.evaluation.reference_free_evaluator}")
    log.info(f"Primary reference-based evaluator: {settings.evaluation.reference_based_evaluator}")
    log.info(f"Deterministic checks active: {settings.deterministic_checks.model_dump()}")
    log.info(f"Quality safety gates active: Quality Threshold >= {settings.thresholds.quality_threshold}")
    yield
    log.info(f"Shutting down {settings.agent.name}")


app = FastAPI(
    title="TalkFlow Translation Quality Agent (Agent 05)",
    version=settings.agent.version,
    description="Independent Translation Quality Agent for autonomous data integrity gating, meaning preservation, and error classification in TalkFlow.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
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
@app.exception_handler(InvalidCandidateError)
async def invalid_candidate_handler(request: Request, exc: InvalidCandidateError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "InvalidCandidateError", "message": exc.message, "details": exc.details},
    )


@app.exception_handler(EvaluatorUnavailableError)
async def evaluator_unavailable_handler(request: Request, exc: EvaluatorUnavailableError):
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"error": "EvaluatorUnavailableError", "message": exc.message, "details": exc.details},
    )


@app.exception_handler(QualityAgentError)
async def generic_qa_error_handler(request: Request, exc: QualityAgentError):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "QualityAgentError", "message": exc.message, "details": exc.details},
    )


# Attach API & WebSocket Routers
app.include_router(router)
app.include_router(ws_router)

