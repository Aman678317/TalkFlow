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
import sys
from collections.abc import AsyncGenerator
from functools import lru_cache
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parent.parent
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

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
        allow_origin_regex=settings.cors_allow_origin_regex,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Trace-ID", "Retry-After"],
    )
    from app.middleware import CSRFMiddleware, RequestContextMiddleware
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    # ---- routers ----
    from app.realtime.ws import router as ws_router
    from app.routers import (
        assistant as assistant_routers,
        auth, contacts, documents, health, meetings, orgs, platform, translate,
        customization, write, v2_v3, telephony, agent_studio, notes, google_meet,
    )
    app.include_router(v2_v3.router)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(orgs.router)
    app.include_router(translate.router)
    app.include_router(write.router)
    app.include_router(customization.router)
    app.include_router(notes.router, prefix="/api/v1")
    app.include_router(documents.router)
    app.include_router(meetings.router)
    app.include_router(meetings.voice_router)
    app.include_router(google_meet.router)
    app.include_router(assistant_routers.chat_router)
    app.include_router(assistant_routers.assistant_router)
    app.include_router(assistant_routers.agent_router)
    app.include_router(agent_studio.router)
    app.include_router(telephony.router)
    app.include_router(contacts.router)
    app.include_router(contacts.campaign_router)
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

    try:
        from app.agent import mount_copilotkit_agent
        mount_copilotkit_agent(app, path="/api/copilotkit")
        log.info("Mounted CopilotKit LangGraph agent at /api/copilotkit")
    except Exception as exc:
        log.warning("Could not mount CopilotKit agent: %s", exc)

    @app.get("/api", include_in_schema=False)
    @app.get("/api-docs", include_in_schema=False)
    async def _api_docs_redirect():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/api/docs")

    web_dist: Path | None = None
    for cand in [
        Path("/app/apps/web/dist"),
        _APP_ROOT.parent.parent / "apps" / "web" / "dist",
        _APP_ROOT / "apps" / "web" / "dist",
        Path("apps/web/dist"),
        Path("../../apps/web/dist"),
    ]:
        if cand.is_dir() and (cand / "index.html").is_file():
            web_dist = cand.resolve()
            break

    if web_dist:
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import FileResponse

        assets_dir = web_dist / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/", include_in_schema=False)
        async def _serve_spa_root():
            return FileResponse(str(web_dist / "index.html"))

        @app.get("/{full_path:path}", include_in_schema=False)
        async def _serve_spa(full_path: str):
            first_segment = full_path.split("/")[0]
            if first_segment in {"api", "api-docs", "docs", "redoc", "openapi.json", "health", "ready", "metrics", "ws", "v2", "v3"}:
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail="Not Found")
            target = web_dist / full_path
            if target.is_file():
                return FileResponse(str(target))
            return FileResponse(str(web_dist / "index.html"))
    else:
        @app.get("/", include_in_schema=False)
        async def _root():
            return {
                "name": settings.app_name,
                "status": "running",
                "version": settings.version,
                "docs": "/api/docs",
            }

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

    # Model warm pool (remediation P1): pre-load configured STT/MT/TTS weights in
    # the background so the first realtime call does not pay model-load latency.
    # Best effort — a warmup failure never blocks startup; providers still
    # lazy-load on first use.
    async def _warm_models() -> None:
        try:
            await ai.warmup()
            log.info("model warmup complete")
        except Exception:
            log.exception("model warmup failed (non-fatal)")

    app.state.warmup_task = asyncio.create_task(_warm_models())

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

    # Asterisk ARI events (P4 adapter; opt-in): the consumer reads the
    # authenticated ARI WebSocket — NOT an HTTP webhook — and maps events onto
    # call states (see app/telephony/ari_events.py). Best effort: a consumer
    # failure must never block startup, and nothing here fabricates call state.
    if settings.asterisk_telephony_enabled:
        try:
            from app.telephony.ari_events import AsteriskARIEventConsumer
            from app.telephony.service import get_telephony_service

            asterisk = get_telephony_service().get_registered_provider("asterisk")
            # P3 marathon follow-up (opt-in): the agent media runtime binds the
            # WS media server Asterisk dials per externalMedia channel and
            # drives the AI-agent turn loop for connected ai_agent calls.
            on_connected = None
            if settings.asterisk_media_enabled:
                try:
                    from app.telephony.media.agent_media_session import (
                        AsteriskAgentMediaRuntime,
                    )

                    media_runtime = AsteriskAgentMediaRuntime.from_settings(
                        provider=asterisk)
                    await media_runtime.start()
                    app.state.asterisk_media_runtime = media_runtime
                    on_connected = media_runtime.on_call_connected
                    log.info(
                        "agent media runtime started on %s:%s "
                        "(turn loop armed for ai_agent calls)",
                        settings.asterisk_media_bind_host,
                        settings.asterisk_media_bind_port,
                    )
                except Exception:  # noqa: BLE001 — media lane is opt-in; startup must not fail
                    log.exception(
                        "failed to start agent media runtime (non-fatal); "
                        "calls keep working signaling-only")
            consumer = AsteriskARIEventConsumer.from_settings(
                provider=asterisk, on_connected=on_connected)
            # D3 ops honesty: the consumer OBJECT is stashed next to its
            # task so /admin/telephony-ops can report whether the inbound
            # intake hook was really attached (configured-vs-armed) and
            # whether the consumer task died after startup.
            app.state.asterisk_ari_consumer = consumer
            app.state.asterisk_ari_task = consumer.start()
            log.info("Asterisk ARI event consumer started (feature flag enabled)")
        except Exception:  # noqa: BLE001 — adapter is opt-in; startup must not fail
            log.exception("failed to start Asterisk ARI event consumer (non-fatal)")

    # P4 auto-dial worker (opt-in): due pending call jobs are executed
    # automatically through the same consent/DNC/window gate as operator
    # claims. At-least-once queue delivery is made safe by execute_job's
    # atomic pending->placing claim (one winner per job).
    if settings.call_worker_enabled:
        from app.telephony.call_worker import (
            JOB_TYPE,
            QUEUE_NAME,
            CallJobTicker,
            handle_calljob_execute,
        )

        call_wr = WorkerRunner(queue(), QUEUE_NAME)
        call_wr.register(JOB_TYPE, handle_calljob_execute)
        call_wr.start()
        app.state.workers.append(call_wr)
        app.state.call_job_ticker_task = CallJobTicker().start()
        log.info("call-job auto-dial worker started (feature flag enabled)")

    # §E2 durable escalation transport: the shared dispatcher gains a
    # best-effort DB store and unresolved tickets rehydrate at boot, so a
    # process restart doesn't strand escalated calls. Both steps are
    # best-effort — a DB problem logs an honest persist-failed ledger event
    # and the live queue remains the working view (never blocks startup).
    try:
        from app.telephony.escalation import EscalationDispatcher, rewire_shared_dispatcher
        from app.telephony.escalation_store import (
            DBEscalationStore,
            rehydrate_shared_dispatcher,
        )

        rewire_shared_dispatcher(EscalationDispatcher(store=DBEscalationStore()))
        restored = await rehydrate_shared_dispatcher()
        if restored:
            log.info("escalation transport rehydrated %d unresolved ticket(s)",
                     restored)
    except Exception:  # noqa: BLE001 — transport is opt-in durability; startup must not fail
        log.exception("escalation transport init failed (non-fatal)")

    # periodic: retention sweep hourly, usage-threshold checks every 10m
    from app.realtime.ws import session_sweeper
    app.state.sweeper = asyncio.create_task(session_sweeper())
    app.state.retention_task = asyncio.create_task(_retention_loop())

    log.info("startup complete")


@lru_cache(maxsize=1)
def _migration_head_revision() -> str:
    """Head revision read from the Alembic script directory.

    The production gate compares against this instead of a literal so it moves
    with `alembic upgrade head`: a new revision tightens the gate automatically
    instead of stranding the deployment on a stale constant."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    api_root = Path(__file__).resolve().parents[1]  # services/api
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    if not head:
        raise RuntimeError("Could not resolve an Alembic head revision from services/api/alembic.")
    return head


async def _ensure_schema() -> None:
    """Dev/test convenience: create tables if migrations haven't run.
    Production REQUIRES alembic upgrade head (schema drift fails closed)."""
    from sqlalchemy import inspect, text
    from app.db.session import engine
    from app.db.base import Base
    import app.db.models  # noqa: F401

    if not settings.is_production:
        async with engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return

    # Production gate: Fail closed if migrations have not been applied up to head
    expected_head = _migration_head_revision()
    async with engine().connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        if "alembic_version" not in tables or "users" not in tables:
            raise RuntimeError("Database schema uninitialized. Run `alembic upgrade head` before booting production.")

        result = await conn.execute(text("SELECT version_num FROM alembic_version"))
        current_rev = result.scalar_one_or_none()
        if current_rev != expected_head:
            raise RuntimeError(
                f"Database migration version mismatch in production: found '{current_rev}', expected '{expected_head}'. "
                "Run `alembic upgrade head` to apply pending migrations."
            )


async def _lifespan_shutdown(app: FastAPI) -> None:
    log.info("shutting down")
    media_runtime = getattr(app.state, "asterisk_media_runtime", None)
    if media_runtime is not None:
        with contextlib.suppress(Exception):
            await media_runtime.stop()
    for w in getattr(app.state, "workers", []):
        await w.stop()
    for t in (getattr(app.state, "sweeper", None),
              getattr(app.state, "retention_task", None),
              getattr(app.state, "asterisk_ari_task", None),
              getattr(app.state, "call_job_ticker_task", None)):
        if t:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t
    from app.realtime.session_manager import manager
    for sid in list(manager._sessions.keys()):
        await manager.close_session(sid)
    from app.queue import close_queue
    await close_queue()
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
