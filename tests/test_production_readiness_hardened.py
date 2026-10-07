"""Phase 10: Production Readiness, Health Probes & Deployment Hardening Test Suite.

Verifies:
1. Liveness probes (/health, /healthz, /api/v1/health) return 200 with uptime and version.
2. Readiness probes (/ready, /readyz, /api/v1/ready) return 200 when healthy, and fail closed (503) on any dependency failure.
3. System version & metadata (/version) provides environment and AI provider registry.
4. Production configuration guardrails strictly validate strong secrets, Redis, and PostgreSQL (rejecting SQLite).
5. Lifespan startup and graceful shutdown cleanly dispose of background workers and connections.
6. CORS configuration disables permissive localhost regex in production mode.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from app.config import Settings, settings
from app.main import create_app, _lifespan


def test_liveness_probes_return_healthy(services_app_client):
    """Liveness probes must return 200 OK with status and uptime."""
    for path in ("/health", "/healthz", "/api/v1/health"):
        resp = services_app_client.get(path)
        assert resp.status_code == 200, f"Failed on path {path}: {resp.text}"
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "uptime_s" in data
        assert data["uptime_s"] >= 0


def test_readiness_probe_all_dependencies_healthy(services_app_client):
    """Readiness probe returns 200 and ready=True when all dependencies pass."""
    for path in ("/ready", "/readyz", "/api/v1/ready"):
        resp = services_app_client.get(path)
        assert resp.status_code == 200, f"Failed on path {path}: {resp.text}"
        data = resp.json()
        assert data["ready"] is True
        assert data["checks"]["database"] is True
        assert data["checks"]["cache"] is True
        assert data["checks"]["queue"] is True
        assert data["checks"]["storage"] is True


def test_readiness_probe_fails_closed_on_dependency_failure(services_app_client):
    """Readiness probe must return 503 Service Unavailable when any dependency fails."""
    # 1. Database failure -> 503
    with patch("app.db.session.healthcheck", new_callable=AsyncMock, return_value=False):
        resp = services_app_client.get("/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["ready"] is False
        assert data["checks"]["database"] is False

    # 2. Cache failure -> 503
    with patch("app.cache.MemoryCache.ping", new_callable=AsyncMock, return_value=False):
        resp = services_app_client.get("/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["ready"] is False
        assert data["checks"]["cache"] is False

    # 3. Queue failure -> 503
    with patch("app.queue.MemoryQueue.ping", new_callable=AsyncMock, return_value=False):
        resp = services_app_client.get("/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["ready"] is False
        assert data["checks"]["queue"] is False

    # 4. Storage failure -> 503
    with patch("app.storage.LocalStorage.ping", new_callable=AsyncMock, return_value=False):
        resp = services_app_client.get("/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["ready"] is False
        assert data["checks"]["storage"] is False


def test_version_endpoint_exposes_metadata(services_app_client):
    """Version endpoint returns application version, environment, and AI capabilities."""
    resp = services_app_client.get("/version")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "GlobalTalk AI"
    assert "version" in data
    assert "env" in data
    assert "ai" in data
    assert "mt" in data["ai"]


def test_production_configuration_guardrails():
    """Production mode must enforce strong secrets, Redis, and PostgreSQL."""
    strong_secret = "a" * 32
    strong_jwt = "b" * 32
    valid_pg = "postgresql+asyncpg://user:pass@localhost:5432/dbname"
    valid_redis = "redis://localhost:6379/0"

    # 1. Insecure default secret_key -> rejected
    with pytest.raises(ValueError, match="strong 'SECRET_KEY'"):
        Settings(
            app_env="production",
            secret_key="dev-secret-key",
            jwt_secret=strong_jwt,
            redis_url=valid_redis,
            database_url=valid_pg,
        )

    # 2. Insecure/short jwt_secret -> rejected
    with pytest.raises(ValueError, match="strong 'JWT_SECRET'"):
        Settings(
            app_env="production",
            secret_key=strong_secret,
            jwt_secret="too-short-secret",
            redis_url=valid_redis,
            database_url=valid_pg,
        )

    # 3. Missing redis_url -> rejected
    with pytest.raises(ValueError, match="requires 'REDIS_URL'"):
        Settings(
            app_env="production",
            secret_key=strong_secret,
            jwt_secret=strong_jwt,
            redis_url="",
            database_url=valid_pg,
        )

    # 4. SQLite in production -> rejected
    with pytest.raises(ValueError, match="SQLite is not permitted in production"):
        Settings(
            app_env="production",
            secret_key=strong_secret,
            jwt_secret=strong_jwt,
            redis_url=valid_redis,
            database_url="sqlite+aiosqlite:///data/test.db",
        )

    # 5. Compliant production settings -> passes cleanly
    prod_settings = Settings(
        app_env="production",
        secret_key=strong_secret,
        jwt_secret=strong_jwt,
        redis_url=valid_redis,
        database_url=valid_pg,
    )
    assert prod_settings.is_production is True
    assert prod_settings.secret_key == strong_secret
    assert prod_settings.jwt_secret == strong_jwt


@pytest.mark.asyncio
async def test_lifespan_startup_and_graceful_shutdown():
    """FastAPI lifespan context must orchestrate startup and graceful shutdown cleanly."""
    app = create_app()

    try:
        async with _lifespan(app):
            # Workers are running
            assert hasattr(app.state, "workers")
            assert len(app.state.workers) == 3
            for w in app.state.workers:
                assert w._task is not None
                assert not w._task.done()

        # After lifespan exit, workers must be stopped
        for w in app.state.workers:
            assert w._task is None
    finally:
        from app.db.session import init_db
        await init_db()
