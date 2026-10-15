"""Tests for the process-wide async database lifecycle."""

from unittest.mock import AsyncMock

import pytest

import app.db.session as db_session_module


@pytest.mark.asyncio
async def test_close_db_keeps_shared_engine_until_last_owner(monkeypatch):
    """One app shutdown must not break another app using the shared engine."""
    engine = type("Engine", (), {"dispose": AsyncMock()})()
    monkeypatch.setattr(db_session_module, "_engine", engine)
    monkeypatch.setattr(db_session_module, "_sessionmaker", object())
    monkeypatch.setattr(db_session_module, "_db_users", 2)

    await db_session_module.close_db()

    assert db_session_module._engine is engine
    assert db_session_module._sessionmaker is not None
    assert db_session_module._db_users == 1
    engine.dispose.assert_not_awaited()

    await db_session_module.close_db()

    assert db_session_module._engine is None
    assert db_session_module._sessionmaker is None
    assert db_session_module._db_users == 0
    engine.dispose.assert_awaited_once()
