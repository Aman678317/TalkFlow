"""Pytest configuration — boots the full app against a temp SQLite database
with dev AI providers. No external services required."""
from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services" / "api"))

_TMP = Path(tempfile.mkdtemp(prefix="gt_test_"))
os.environ.update({
    "APP_ENV": "test",
    "GT_ENV_FILE": "",  # ignore .env files; explicit env only
    "DATABASE_URL": f"sqlite+aiosqlite:///{_TMP}/test.db",
    "FALLBACK_DATABASE_URL": "",
    "REDIS_URL": "",
    "CACHE_BACKEND": "memory",
    "S3_ENABLED": "false",
    "LOCAL_STORAGE_PATH": str(_TMP / "storage"),
    "MODEL_CACHE_PATH": str(_TMP / "models"),
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
})


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


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
def client(app):
    """TestClient runs startup/shutdown lifespan and supports WebSockets."""
    from starlette.testclient import TestClient
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def user(client) -> dict:
    """Fresh signed-up user + org per test."""
    email = f"u_{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/api/v1/auth/signup", json={
        "email": email, "password": "testpass123", "name": "Test User",
        "organization_name": f"Org {uuid.uuid4().hex[:6]}"})
    assert r.status_code == 201, r.text
    data = r.json()
    return {
        "email": email,
        "token": data["tokens"]["access_token"],
        "refresh": data["tokens"]["refresh_token"],
        "user_id": data["user"]["id"],
        "org_id": data["organization"]["id"],
        "headers": {"Authorization": f"Bearer {data['tokens']['access_token']}"},
    }


@pytest.fixture()
def second_user(client) -> dict:
    email = f"u2_{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/api/v1/auth/signup", json={
        "email": email, "password": "testpass123", "name": "Second User",
        "organization_name": f"Org2 {uuid.uuid4().hex[:6]}"})
    assert r.status_code == 201, r.text
    data = r.json()
    return {
        "email": email,
        "token": data["tokens"]["access_token"],
        "headers": {"Authorization": f"Bearer {data['tokens']['access_token']}"},
        "org_id": data["organization"]["id"],
    }
