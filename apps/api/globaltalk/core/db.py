"""Database engine/session management. SQLite for dev, PostgreSQL for prod (same models)."""
from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from globaltalk.core.config import settings


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    """The one URL resolution, shared by the engine and alembic/env.py.

    They used to diverge — the engine preferred GLOBALTALK_DATABASE_URL while
    env.py read settings.database_url — so `alembic upgrade head` could migrate a
    different database than the process boots against."""
    url = os.environ.get("GLOBALTALK_DATABASE_URL") or settings.database_url
    if "+aiosqlite" in url:
        url = url.replace("+aiosqlite", "")
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        # resolve relative SQLite paths against the repo root (CWD-independent)
        rel = url[len("sqlite:///"):]
        url = f"sqlite:///{settings.resolve(rel)}"
    return url


def _make_engine():
    url = database_url()
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        kwargs.update({"connect_args": {"check_same_thread": False, "timeout": 30}})
        engine = create_engine(url, **kwargs)

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _rec):  # pragma: no cover
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=15000")
            cur.close()
    else:
        kwargs.update({"pool_size": 10, "max_overflow": 20})
        engine = create_engine(url, **kwargs)
    return engine


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Create tables when DB_AUTOCREATE (dev convenience). Prod uses `alembic upgrade head`."""
    import globaltalk.models  # noqa: F401  (register mappers)
    if settings.is_production:
        # A worker booting against an unmigrated database otherwise "fixes" the
        # schema with create_all + raw ALTER TABLE and quietly diverges it from
        # the migration lineage that the API owns.
        _require_migrations_applied()
        return
    if settings.db_autocreate:
        Base.metadata.create_all(bind=engine)


def _require_migrations_applied() -> None:
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    tables = set(insp.get_table_names())
    if "alembic_version_globaltalk" not in tables or "users" not in tables:
        raise RuntimeError(
            "Database schema uninitialized. Run `alembic upgrade head` in apps/api "
            "before booting production."
        )
    with engine.begin() as conn:
        current = conn.execute(
            text("SELECT version_num FROM alembic_version_globaltalk")
        ).scalar_one_or_none()
    expected = migration_head_revision()
    if current != expected:
        raise RuntimeError(
            f"Database migration version mismatch in production: found '{current}', "
            f"expected '{expected}'. Run `alembic upgrade head` to apply pending migrations."
        )


def migration_head_revision() -> str:
    """Head of the apps/api Alembic lineage, read from disk so the boot gate
    tracks the migrations instead of a literal that rots."""
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    api_root = Path(__file__).resolve().parents[2]  # apps/api
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    if not head:
        raise RuntimeError("Could not resolve an Alembic head revision from apps/api/alembic.")
    return head
