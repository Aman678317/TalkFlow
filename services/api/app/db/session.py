"""Async engine/session factory with pooling + tenant-scoped helpers."""
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine)

from app.config import settings

log = logging.getLogger("app.db")

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None
_db_users = 0


def _normalize_db_url(url: str) -> str:
    if not url:
        return url
    if url.startswith("sqlite://") and not url.startswith("sqlite+"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql+psycopg://"):
        url = url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql+psycopg2://"):
        url = url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)

    # Supabase / cloud PG often includes sslmode=require which asyncpg rejects as unknown keyword
    if "asyncpg" in url:
        url = url.replace("sslmode=require", "ssl=require")
        url = url.replace("sslmode=prefer", "ssl=prefer")
        url = url.replace("sslmode=disable", "ssl=disable")
        # asyncpg does not accept 'pgbouncer' as a keyword argument (Prisma-specific query param)
        if "pgbouncer" in url.lower():
            from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
            parts = urlsplit(url)
            filtered_params = [
                (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                if k.lower() != "pgbouncer"
            ]
            new_query = urlencode(filtered_params)
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))
    return url


def _make_engine(url: str) -> AsyncEngine:
    is_pooler = ":6543" in url or "pooler.supabase.com" in url or "pgbouncer" in url.lower()
    url = _normalize_db_url(url)
    kwargs: dict = {"echo": settings.db_echo, "future": True}
    if "postgresql" in url:
        connect_args: dict = {}
        # Supabase transaction pooler (port 6543) or pgBouncer requires disabling statement cache
        if is_pooler or ":6543" in url or "pooler.supabase.com" in url:
            connect_args.update({
                "statement_cache_size": 0,
                "prepared_statement_cache_size": 0,
            })
        if connect_args:
            kwargs["connect_args"] = connect_args

        if settings.app_env == "test":
            from sqlalchemy.pool import NullPool
            kwargs.update(poolclass=NullPool)
        else:
            kwargs.update(pool_size=settings.db_pool_size,
                          max_overflow=settings.db_max_overflow,
                          pool_pre_ping=True, pool_recycle=300)
    elif "sqlite" in url:
        if settings.app_env == "test":
            from sqlalchemy.pool import NullPool
            kwargs.update(poolclass=NullPool)

    engine = create_async_engine(url, **kwargs)
    if "sqlite" in url:
        from sqlalchemy import event

        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            try:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=60000")
                cursor.close()
            except Exception:
                pass

    return engine


async def init_db() -> None:
    """Create engine; fall back to SQLite in non-production if PG is down."""
    global _engine, _sessionmaker, _db_users
    # Multiple FastAPI app instances can share this process (for example, a
    # test suite may have more than one TestClient alive at once).  The engine
    # and session factory are process-wide, so each app must acquire a
    # reference rather than replacing the shared state.
    if _engine is not None and _sessionmaker is not None:
        _db_users += 1
        return

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
    _db_users = 1
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
    global _engine, _sessionmaker, _db_users
    if _engine is None:
        _sessionmaker = None
        _db_users = 0
        return

    if _db_users > 1:
        _db_users -= 1
        return

    await _engine.dispose()
    _engine = None
    _sessionmaker = None
    _db_users = 0


async def healthcheck() -> bool:
    try:
        async with engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
