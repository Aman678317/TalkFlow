"""Pytest configuration and test fixtures."""
from __future__ import annotations

import sys
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient

# Add project root to sys.path so app imports work cleanly
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

