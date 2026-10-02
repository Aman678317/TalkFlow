"""Async engine/session factory with pooling + tenant-scoped helpers."""
from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine)

from app.config import settings

log = logging.getLogger("app.db")

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _normalize_db_url(url: str) -> str:
    if url.startswith("sqlite://") and not url.startswith("sqlite+"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _make_engine(url: str) -> AsyncEngine:
    url = _normalize_db_url(url)
    kwargs: dict = {"echo": settings.db_echo, "future": True}
    if "postgresql" in url:
        kwargs.update(pool_size=settings.db_pool_size,
                      max_overflow=settings.db_max_overflow,
                      pool_pre_ping=True, pool_recycle=1800)
    return create_async_engine(url, **kwargs)


async def init_db() -> None:
    """Create engine; fall back to SQLite in non-production if PG is down."""
    global _engine, _sessionmaker
    url = settings.database_url
    try:
        engine = _make_engine(url)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        if settings.is_production or not settings.fallback_database_url:
            raise
        log.warning("primary database unavailable (%s); using fallback %s",
                    type(e).__name__, settings.fallback_database_url)
        url = settings.fallback_database_url
        engine = _make_engine(url)
    _engine = engine
    _sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    log.info("database ready: %s", url.split("@")[-1])


def engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("database not initialized")
    return _engine


def sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("database not initialized")
    return _sessionmaker


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency."""
    async with sessionmaker()() as session:
        yield session


@asynccontextmanager
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Service/worker context manager."""
    async with sessionmaker()() as session:
        yield session


async def close_db() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def healthcheck() -> bool:
    try:
        async with engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
