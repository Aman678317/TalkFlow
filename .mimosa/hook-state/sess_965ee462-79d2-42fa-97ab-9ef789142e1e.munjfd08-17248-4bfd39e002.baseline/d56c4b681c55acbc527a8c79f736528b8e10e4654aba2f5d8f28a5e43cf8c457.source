"""FastAPI application factory. Control plane + data plane entrypoints, worker wiring,
OpenAPI docs, CORS, security middleware."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from globaltalk.api.v1 import health as health_routes
from globaltalk.api.v1.auth import router as auth_router
from globaltalk.api.v1.documents import router as documents_router
from globaltalk.api.v1.languages import glossary_router, router as languages_router
from globaltalk.api.v1.languages import style_router, tm_router
from globaltalk.api.v1.meetings import router as meetings_router
from globaltalk.api.v1.platform import admin_router, bridge_router
from globaltalk.api.v1.platform import router as platform_router
from globaltalk.api.v1.translate import router as translate_router
from globaltalk.core.config import settings
from globaltalk.core.db import init_db
from globaltalk.core.errors import register_error_handlers
from globaltalk.core.logging import get_logger, setup_logging
from globaltalk.core.middleware import RequestContextMiddleware
from globaltalk.realtime.ws import router as ws_router

log = get_logger("app")


def _register_workers() -> None:
    from globaltalk.core.queue import QUEUE_DOCUMENTS, QUEUE_WEBHOOKS, register_handler

    def handle_document(job: dict) -> None:
        from globaltalk.core.db import SessionLocal
        from globaltalk.services.documents import process_document
        db = SessionLocal()
        try:
            process_document(db, job["document_id"])
        finally:
            db.close()

    def handle_webhook(job: dict) -> None:
        import time as _t
        if job.get("delay_s"):
            _t.sleep(min(job["delay_s"], 5))  # local dev: shorten; prod uses Redis delayed set
        from globaltalk.core.db import SessionLocal
        from globaltalk.services.webhooks import deliver
        db = SessionLocal()
        try:
            deliver(db, job["delivery_id"])
        finally:
            db.close()

    register_handler(QUEUE_DOCUMENTS, handle_document)
    register_handler(QUEUE_WEBHOOKS, handle_webhook)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.log_level)
    init_db()
    _register_workers()
    from ai.memory_guard import start as start_memory_guard
    start_memory_guard()
    from globaltalk.seed import seed_all
    seed_all()
    # warm AI providers in background (models load lazily on first use; warming avoids
    # first-request latency spikes)
    import threading

    def warm():
        try:
            from globaltalk.core.db import SessionLocal
            from globaltalk.services.capabilities import refresh_from_providers
            db = SessionLocal()
            try:
                refresh_from_providers(db)  # lightweight probes only — no weight loading
            finally:
                db.close()
        except Exception:
            log.warning("capability_refresh_skipped")
        try:
            from ai.bootstrap import get_router
            r = get_router()
            r.health("mt", "argos")
            r.health("langid", "langid")
        except Exception:
            log.warning("ai_warmup_skipped")

    threading.Thread(target=warm, daemon=True, name="ai-warmup").start()
    log.info("api_started", extra={"env": settings.app_env, "db": settings.database_url})
    yield
    log.info("api_stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="GlobalTalk AI API",
        description=(
            "Multilingual AI communication platform. One shared conversation: every "
            "participant speaks and hears their own language. The canonical human source "
            "is immutable; all translations are derivative artifacts (source_segment_id).\n\n"
            "**Auth**: `Authorization: Bearer <JWT>` (user) or `X-API-Key: gtk_...` "
            "(developer API key).\n\n"
            "**Realtime**: WebSocket `/ws/meetings/{meeting_id}` — see docs/REALTIME.md "
            "for the versioned event protocol.\n\n"
            "**Webhooks**: HMAC-SHA256 signed (`GlobalTalk-Signature: v1=...`, "
            "`GlobalTalk-Timestamp`), retried with backoff."),
        version="0.1.0",
        lifespan=lifespan,
        servers=[{"url": settings.api_base_url}],
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-Id",
                       "X-Trace-Id", "X-Org-Id"],
        expose_headers=["X-Request-Id", "X-Trace-Id"],
    )
    register_error_handlers(app)

    app.include_router(health_routes.router)  # /health /ready /version /metrics /internal/*
    app.include_router(ws_router)             # /ws/meetings/{id}

    from fastapi import APIRouter
    v1 = APIRouter(prefix="/api/v1")
    v1.include_router(auth_router)
    v1.include_router(translate_router)
    v1.include_router(languages_router)
    v1.include_router(glossary_router)
    v1.include_router(tm_router)
    v1.include_router(style_router)
    v1.include_router(documents_router)
    v1.include_router(meetings_router)
    v1.include_router(platform_router)
    v1.include_router(bridge_router)
    v1.include_router(admin_router)
    app.include_router(v1)

    return app


app = create_app()
