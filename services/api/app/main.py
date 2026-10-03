"""GlobalTalk AI — FastAPI application entrypoint.

Control plane (auth/orgs/billing/config) and data plane (translation,
realtime sessions, documents) live in one deployable for the MVP; module
boundaries keep them separable into services later (PDD §59). Heavy AI
inference NEVER runs in request handlers — it runs in the gt_ai provider
layer (thread-offloaded) and in queue workers.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.config import settings
from app.errors import register_error_handlers
from app.logging_conf import setup_logging

log = logging.getLogger("app.main")


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    await _lifespan_startup(app)
    try:
        yield
    finally:
        await _lifespan_shutdown(app)


def create_app() -> FastAPI:
    setup_logging(settings.log_level)
    app = FastAPI(
        title="GlobalTalk AI API",
        description=(
            "Multilingual AI communication platform: text & document translation, "
            "realtime voice translation with per-listener language routing, "
            "meetings, chat, glossaries, translation memory, and a developer API.\n\n"
            "**Core rule:** the human source segment is canonical; translations "
            "fan out per listener and never become a new semantic source."
        ),
        version=settings.version,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=_lifespan,
    )

    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$" if not settings.is_production else None,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Trace-ID", "Retry-After"],
    )
    from app.middleware import RequestContextMiddleware
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    # ---- routers ----
    from app.realtime.ws import router as ws_router
    from app.routers import (
        assistant as assistant_routers,
        auth, documents, health, meetings, orgs, platform, translate,
        customization, write, v2_v3, telephony,
    )
    app.include_router(v2_v3.router)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(orgs.router)
    app.include_router(translate.router)
    app.include_router(write.router)
    app.include_router(customization.router)
    app.include_router(documents.router)
    app.include_router(meetings.router)
    app.include_router(meetings.voice_router)
    app.include_router(assistant_routers.chat_router)
    app.include_router(assistant_routers.assistant_router)
    app.include_router(assistant_routers.agent_router)
    app.include_router(telephony.router)
    # Technical specification alias: /api/voice/* endpoints
    voice_alias_router = APIRouter(prefix="/api/voice", tags=["voice-aliases"])
    voice_alias_router.add_api_route("/token", telephony.get_voice_access_token, methods=["GET"])
    voice_alias_router.add_api_route("/incoming", telephony.telephony_voice_webhook, methods=["POST"])
    voice_alias_router.add_api_route("/status", telephony.telephony_status_webhook, methods=["POST"])
    app.include_router(voice_alias_router)

    for r in (platform.keys_router, platform.usage_router, platform.webhooks_router,
              platform.search_router, platform.feedback_router, platform.flags_router,
              platform.integrations_router, platform.admin_router):
        app.include_router(r)
    app.include_router(ws_router)

    @app.get("/", include_in_schema=False)
    async def _root():
        return {
            "name": settings.app_name,
            "status": "running",
            "version": settings.version,
            "docs": "/api/docs",
        }

    @app.get("/api", include_in_schema=False)
    @app.get("/api-docs", include_in_schema=False)
    async def _api_docs_redirect():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/api/docs")

    return app


async def _lifespan_startup(app: FastAPI) -> None:
    log.info("starting %s v%s (%s)", settings.app_name, settings.version, settings.app_env)
    # datastores
    from app.db.session import init_db
    await init_db()
    from app.cache import init_cache
    await init_cache(settings)
    from app.queue import init_queue
    await init_queue(settings)
    from app.storage import init_storage
    await init_storage()

    # auto-migrate schema in dev/test when tables are missing
    await _ensure_schema()

    # seed defaults if empty (idempotent)
    from app.seed import run_seed
    await run_seed()

    # AI layer
    from app.ai import ai
    from app.db.session import db_session
    async with db_session() as db:
        await ai.load_registry(db)

    # workers
    app.state.workers = []
    from app.queue import WorkerRunner, queue
    from app.services import document_service, webhook_service
    doc_worker = WorkerRunner(queue(), "documents")
    doc_worker.register("document.process", document_service.process_document_job)
    doc_worker.start()
    app.state.workers.append(doc_worker)
    wh_worker = WorkerRunner(queue(), "webhooks")
    wh_worker.register("webhook.deliver", webhook_service.deliver_job)
    wh_worker.start()
    app.state.workers.append(wh_worker)
    default_worker = WorkerRunner(queue(), "default")
    default_worker.register("retention.sweep", _retention_job)
    default_worker.register("billing.finalize", _billing_job)
    default_worker.start()
    app.state.workers.append(default_worker)

    # periodic: retention sweep hourly, usage-threshold checks every 10m
    from app.realtime.ws import session_sweeper
    app.state.sweeper = asyncio.create_task(session_sweeper())
    app.state.retention_task = asyncio.create_task(_retention_loop())

    log.info("startup complete")


async def _ensure_schema() -> None:
    """Dev/test convenience: create tables if migrations haven't run.
    Production REQUIRES alembic upgrade head (schema drift fails loudly)."""
    from sqlalchemy import inspect, text
    from app.db.session import engine
    from app.db.base import Base
    import app.db.models  # noqa: F401
    if not settings.is_production:
        async with engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            def _patch_schema(sync_conn):
                insp = inspect(sync_conn)
                tables = insp.get_table_names()
                if "language_capabilities" in tables:
                    l_cols = {c["name"] for c in insp.get_columns("language_capabilities")}
                    col_defs = [
                        ("script", "VARCHAR(16) DEFAULT 'Latn'"),
                        ("rtl", "BOOLEAN DEFAULT 0"),
                        ("translation_status", "VARCHAR(16) DEFAULT 'SUPPORTED'"),
                        ("speech_input_status", "VARCHAR(16) DEFAULT 'EXPERIMENTAL'"),
                        ("speech_output_status", "VARCHAR(16) DEFAULT 'EXPERIMENTAL'"),
                        ("realtime_status", "VARCHAR(16) DEFAULT 'EXPERIMENTAL'"),
                        ("document_status", "VARCHAR(16) DEFAULT 'SUPPORTED'"),
                        ("wer_benchmark", "FLOAT"),
                        ("mt_quality_score", "FLOAT"),
                        ("speech_input_supported", "BOOLEAN DEFAULT 0"),
                        ("speech_output_supported", "BOOLEAN DEFAULT 0"),
                        ("translation_supported", "BOOLEAN DEFAULT 0"),
                        ("realtime_supported", "BOOLEAN DEFAULT 0"),
                        ("document_supported", "BOOLEAN DEFAULT 0"),
                        ("stt_status", "VARCHAR(16) DEFAULT 'EXPERIMENTAL'"),
                        ("tts_status", "VARCHAR(16) DEFAULT 'EXPERIMENTAL'"),
                        ("mt_status", "VARCHAR(16) DEFAULT 'EXPERIMENTAL'"),
                    ]
                    for col_name, col_type in col_defs:
                        if col_name not in l_cols:
                            sync_conn.execute(text(f"ALTER TABLE language_capabilities ADD COLUMN {col_name} {col_type}"))
                if "webhook_deliveries" in tables:
                    cols = {c["name"] for c in insp.get_columns("webhook_deliveries")}
                    if "endpoint_id" not in cols:
                        sync_conn.execute(text("ALTER TABLE webhook_deliveries ADD COLUMN endpoint_id VARCHAR(36)"))
                    if "payload_json" not in cols:
                        sync_conn.execute(text("ALTER TABLE webhook_deliveries ADD COLUMN payload_json JSON"))
                    if "last_status_code" not in cols:
                        sync_conn.execute(text("ALTER TABLE webhook_deliveries ADD COLUMN last_status_code INTEGER"))
                    if "next_retry_at" not in cols:
                        sync_conn.execute(text("ALTER TABLE webhook_deliveries ADD COLUMN next_retry_at TIMESTAMP"))
            await conn.run_sync(_patch_schema)
        return
    async with engine().connect() as conn:
        tables = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names())
    if "users" in tables:
        return
    raise RuntimeError("database schema missing — run `alembic upgrade head`")


async def _lifespan_shutdown(app: FastAPI) -> None:
    log.info("shutting down")
    for w in getattr(app.state, "workers", []):
        await w.stop()
    for t in (getattr(app.state, "sweeper", None),
              getattr(app.state, "retention_task", None)):
        if t:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t
    from app.realtime.session_manager import manager
    for sid in list(manager._sessions.keys()):
        await manager.close_session(sid)
    from app.db.session import close_db
    await close_db()


async def _retention_job(payload: dict) -> None:
    from app.db.session import db_session
    from app.services import retention_service
    async with db_session() as db:
        await retention_service.sweep(db)


async def _billing_job(payload: dict) -> None:
    import uuid as _uuid
    from app.db.session import db_session
    from app.services import billing_service
    async with db_session() as db:
        await billing_service.finalize_invoice(
            db, _uuid.UUID(payload["org_id"]),
            payload["period_start"], payload["period_end"])


async def _retention_loop() -> None:
    while True:
        await asyncio.sleep(3600)
        try:
            await _retention_job({})
        except Exception:
            log.exception("retention sweep failed")


app = create_app()
