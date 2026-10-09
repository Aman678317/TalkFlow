"""Alembic environment — reads DATABASE_URL from GlobalTalk settings."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from alembic import context
from globaltalk.core.config import settings
from globaltalk.core.db import Base
import globaltalk.models  # noqa: F401 — register all mappers

config = context.config
_url = settings.database_url
if _url.startswith("sqlite:///") and not _url.startswith("sqlite:////"):
    _url = f"sqlite:///{settings.resolve(_url[len('sqlite:///'):])}"
config.set_main_option("sqlalchemy.url", _url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"),
                      target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"}, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import engine_from_config, pool
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}),
                                     prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        is_sqlite = connection.dialect.name == "sqlite"
        context.configure(connection=connection, target_metadata=target_metadata,
                          render_as_batch=is_sqlite)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
