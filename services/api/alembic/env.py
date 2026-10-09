"""Alembic environment — async engine, metadata from app.db.models."""
from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
import app.db.models  # noqa: E402,F401  (register all tables)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from app.db.session import _normalize_db_url

target_url = (
    config.get_main_option("sqlalchemy.url")
    or os.environ.get("DIRECT_URL")
    or os.environ.get("DATABASE_URL", settings.database_url)
)
is_pooler = (
    ":6543" in (target_url or "")
    or "pooler.supabase.com" in (target_url or "")
    or "pgbouncer" in (target_url or "").lower()
)
db_url = _normalize_db_url(target_url)
# Escape % to %% because Alembic's ConfigParser interprets % as interpolation syntax
config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=db_url, target_metadata=target_metadata, literal_binds=True,
        dialect_opts={"paramstyle": "named"}, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata,
                      compare_type=True, render_as_batch=connection.dialect.name == "sqlite")
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connect_args = {}
    if is_pooler or "pooler.supabase.com" in db_url or ":6543" in db_url:
        connect_args = {
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        }
    engine_kwargs = {
        "poolclass": pool.NullPool,
    }
    if connect_args:
        engine_kwargs["connect_args"] = connect_args

    connectable = create_async_engine(
        db_url,
        **engine_kwargs,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    try:
        asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, run_async_migrations())
            future.result()
    except RuntimeError:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
