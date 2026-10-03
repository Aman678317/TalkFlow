"""Root pytest configuration: isolated test env (SQLite file DB, local storage, memory cache).

Set BEFORE any globaltalk import so pydantic-settings picks up the environment.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_ROOT, "apps", "api"))
sys.path.insert(0, _ROOT)

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("GLOBALTALK_DATABASE_URL", "sqlite:///" + os.path.join(_ROOT, "data", "globaltalk_test.db"))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///" + os.path.join(_ROOT, "data", "services_test.db"))
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("STORAGE_LOCAL_PATH", os.path.join(_ROOT, "data", "test-storage"))
os.environ.setdefault("MODEL_CACHE_PATH", os.environ.get("MODEL_CACHE_PATH",
                                                         "/tmp/globaltalk-models"))
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:1/0")  # unreachable → memory fallback
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-0123456789abcdef0123456789abcdef")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DB_AUTOCREATE", "true")
os.environ.setdefault("MALWARE_SCAN_ENABLED", "false")
os.environ.setdefault("RATE_LIMIT_AUTH", "2000/minute")
os.environ.setdefault("RATE_LIMIT_TRANSLATE", "2000/minute")

os.makedirs(os.path.join(_ROOT, "data"), exist_ok=True)

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def _prepare_db():
    """Fresh schema + seed for the test session."""
    db_file = os.path.join(_ROOT, "data", "globaltalk_test.db")
    if os.path.exists(db_file):
        os.remove(db_file)
    from globaltalk.core.db import init_db
    init_db()
    from globaltalk.seed import seed_all
    seed_all()
    yield


@pytest.fixture()
def db(_prepare_db):
    from globaltalk.core.db import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def client(_prepare_db):
    from fastapi.testclient import TestClient
    from globaltalk.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_client(client):
    """Client authenticated as a freshly signed-up user + org."""
    import uuid
    email = f"test-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/api/v1/auth/signup", json={
        "email": email, "password": "TestPass123!", "full_name": "Test User",
        "organization_name": f"Test Org {uuid.uuid4().hex[:6]}"})
    assert r.status_code == 201, r.text
    token = r.json()["tokens"]["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def make_wav(samples, rate=16000):
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples)
    return buf.getvalue()


def synth_tone(seconds=1.0, freq=220.0, rate=16000, amplitude=0.4):
    import math
    import struct
    n = int(seconds * rate)
    return b"".join(struct.pack("<h", int(amplitude * 32767 *
                                          math.sin(2 * math.pi * freq * i / rate)))
                    for i in range(n))
