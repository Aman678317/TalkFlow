"""Database engine/session management. SQLite for dev, PostgreSQL for prod (same models)."""
from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from globaltalk.core.config import settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    url = settings.database_url
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        # resolve relative SQLite paths against the repo root (CWD-independent)
        rel = url[len("sqlite:///"):]
        url = f"sqlite:///{settings.resolve(rel)}"
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
    if settings.db_autocreate:
        Base.metadata.create_all(bind=engine)
