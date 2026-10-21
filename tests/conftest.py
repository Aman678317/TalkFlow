"""Pytest configuration — boots the full app against a temp SQLite database
with dev AI providers. No external services required."""
from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "ai"))
sys.path.insert(0, str(REPO / "services" / "api"))

_TMP = Path(tempfile.mkdtemp(prefix="gt_test_"))
_raw_db = os.environ.get("DATABASE_URL", "")
if not _raw_db or "sqlite" in _raw_db or "globaltalk.db" in _raw_db:
    _db_url = f"sqlite+aiosqlite:///{_TMP}/services_test.db?timeout=60"
else:
    _db_url = _raw_db

_gt_raw_db = os.environ.get("GLOBALTALK_DATABASE_URL", "")
if not _gt_raw_db or "sqlite" in _gt_raw_db:
    _gt_db_url = f"sqlite:///{_TMP}/globaltalk_test.db"
else:
    _gt_db_url = _gt_raw_db

_redis_url = os.environ.get("REDIS_URL", "")
_cache_backend = os.environ.get("CACHE_BACKEND") or ("memory" if not _redis_url else "redis")
os.environ.update({
    "APP_ENV": "test",
    "GT_ENV_FILE": "",  # ignore .env files; explicit env only
    "DATABASE_URL": _db_url,
    "GLOBALTALK_DATABASE_URL": _gt_db_url,
    "FALLBACK_DATABASE_URL": "",
    "REDIS_URL": _redis_url if _cache_backend != "memory" else "",
    "CACHE_BACKEND": _cache_backend,
    "S3_ENABLED": "false",
    "LOCAL_STORAGE_PATH": str(_TMP / "storage"),
    # An operator-supplied cache (CI's realtime-golden job) must survive: tests/realtime
    # gates the acceptance test on the weights actually downloaded there.
    "MODEL_CACHE_PATH": os.environ.get("MODEL_CACHE_PATH") or str(_TMP / "models"),
    "TRANSLATION_PROVIDER": "dev_echo",
    "STT_PROVIDER": "dev_text",
    "TTS_PROVIDER": "dev_tone",
    "LANG_DETECT_PROVIDER": "langdetect",
    "SUMMARIZATION_PROVIDER": "extractive",
    "EMBEDDING_PROVIDER": "hash_tfidf",
    "JWT_SECRET": "test-jwt-secret-0123456789abcdef0123456789",
    "SECRET_KEY": "test-secret-0123456789abcdef0123456789ab",
    "LIVEKIT_ENABLED": "false",
    "METRICS_ENABLED": "false",
    "RATE_LIMIT_TRANSLATE": "100000/minute",
    "RATE_LIMIT_AUTH": "100000/minute",
    "RATE_LIMIT_DEFAULT": "100000/minute",
    "FF_AGENT_BRIDGE": "true",
    "LOG_LEVEL": "WARNING",
    "BCRYPT_ROUNDS": "4",
})


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session", autouse=True)
def prepare_services_db():
    """Ensure database schema is created and initialized for services tests."""
    from app.db.base import Base
    import app.db.models  # noqa: F401
    from app.db.session import engine, init_db
    import asyncio
    async def _init():
        await init_db()
        async with engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    if loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            executor.submit(asyncio.run, _init()).result()
    else:
        loop.run_until_complete(_init())
    yield


@pytest.fixture(scope="session")
def app():
    from app.config import get_settings
    get_settings.cache_clear()
    import importlib
    import app.config as cfg
    importlib.reload(cfg)
    from app.main import create_app
    return create_app()


@pytest.fixture(scope="session")
def services_app_client(app):
    """TestClient runs startup/shutdown lifespan and supports WebSockets."""
    from starlette.testclient import TestClient
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def user(services_app_client) -> dict:
    """Fresh signed-up user + org per test."""
    email = f"u_{uuid.uuid4().hex[:10]}@example.com"
    r = services_app_client.post("/api/v1/auth/signup", json={
        "email": email, "password": "testpass123", "name": "Test User",
        "organization_name": f"Org {uuid.uuid4().hex[:6]}"})
    assert r.status_code == 201, r.text
    data = r.json()
    return {
        "email": email,
        "token": data["tokens"]["access_token"],
        # Phase 1: the refresh secret is only ever delivered via the HttpOnly cookie,
        # never the JSON body (body refresh_token is blanked). Pull it from the cookie.
        "refresh": r.cookies.get("refresh_token") or data["tokens"].get("refresh_token", ""),
        "user_id": data["user"]["id"],
        "org_id": data["organization"]["id"],
        "headers": {"Authorization": f"Bearer {data['tokens']['access_token']}"},
    }


@pytest.fixture()
def second_user(services_app_client) -> dict:
    email = f"u2_{uuid.uuid4().hex[:10]}@example.com"
    r = services_app_client.post("/api/v1/auth/signup", json={
        "email": email, "password": "testpass123", "name": "Second User",
        "organization_name": f"Org2 {uuid.uuid4().hex[:6]}"})
    assert r.status_code == 201, r.text
    data = r.json()
    return {
        "email": email,
        "token": data["tokens"]["access_token"],
        "user_id": data["user"]["id"],
        "headers": {"Authorization": f"Bearer {data['tokens']['access_token']}"},
        "org_id": data["organization"]["id"],
    }
