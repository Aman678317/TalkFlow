"""Application lifecycle events and graceful shutdown coordination."""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import settings
from app.core.logging import get_logger, setup_logging

log = get_logger("core.lifecycle")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manages application startup and shutdown."""
    setup_logging(debug=settings.agent.debug)
    log.info(f"Starting {settings.agent.name} v{settings.agent.version} on {settings.api.host}:{settings.api.port}")
    log.info(f"Primary Translation Provider: {settings.translation.primary_provider.upper()}")
    log.info(f"Zero-Pivot Translation Invariant: {'ENFORCED' if not settings.routing.allow_pivot_translation else 'PIVOTS ALLOWED'}")
    log.info(f"Agent Brain (Ollama/OpenAI Agents SDK): {'ENABLED (' + settings.llm_agent.model + ')' if settings.llm_agent.enabled else 'DISABLED'}")

    yield

    log.info("Shutting down Neural Translation Agent gracefully...")

