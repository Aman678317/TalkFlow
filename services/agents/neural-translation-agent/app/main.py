"""Main entrypoint for TalkFlow Neural Translation Agent (Agent 04)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router as api_router
from app.api.websocket import ws_router
from app.core.config import settings
from app.core.lifecycle import lifespan

app = FastAPI(
    title="TalkFlow Neural Translation Agent (Agent 04)",
    description="Production-grade AI Neural Translation Agent for multilingual meetings, zero-pivot fan-out, and Hinglish code-switching.",
    version=settings.agent.version,
    lifespan=lifespan,
)

# Enable CORS for local web testing and TalkFlow frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(api_router)
app.include_router(ws_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.api.host, port=settings.api.port, reload=settings.agent.debug)

