"""Phase 7: Database Models & Alembic Migrations Hardening Test Suite.

Verifies:
1. Complete Alembic upgrade pipeline on fresh database without schema drift.
2. Clean downgrade/rollback and re-upgrade execution.
3. Production fail-closed enforcement when migrations are unapplied or version mismatched.
4. Tenancy & foreign key integrity (cascades, unique constraints).
5. The apps/api (legacy worker) lineage is itself complete, and keeps its version
   bookkeeping separate from the API's `alembic_version` that the boot gate reads.

Runs on SQLite by default; the CI `migrations` job points ALEMBIC_TEST_DATABASE_URL
at an empty scratch PostgreSQL database so the same pipeline is proven on the
engine production actually uses.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from pathlib import Path
import pytest
from sqlalchemy import text, inspect, create_engine
from sqlalchemy.ext.asyncio import create_async_engine

from alembic.config import Config
from alembic import command
from alembic.script import ScriptDirectory

from app.config import settings
from app.db.base import Base
from app.db.models import User, Organization, OrganizationMember, UserIdentity, PhoneNumber
from app.db.session import init_db, db_session
from app.main import _ensure_schema, _migration_head_revision


REPO_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI_PATH = str(REPO_ROOT / "services" / "api" / "alembic.ini")
LEGACY_INI_PATH = str(REPO_ROOT / "apps" / "api" / "alembic.ini")
LEGACY_VERSION_TABLE = "alembic_version_globaltalk"


def get_alembic_config(db_url: str) -> Config:
    cfg = Config(ALEMBIC_INI_PATH)
    cfg.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
    return cfg


def get_legacy_alembic_config(db_url: str) -> Config:
    cfg = Config(LEGACY_INI_PATH)
    # script_location in the ini is CWD-relative; pin it to the repo.
    cfg.set_main_option("script_location", str(REPO_ROOT / "apps" / "api" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
    return cfg


def _scratch_url(env_key: str = "ALEMBIC_TEST_DATABASE_URL") -> str:
    return os.environ.get(env_key) or ""


def _is_postgres(url: str) -> bool:
    return bool(url) and not url.startswith("sqlite")


def _connect(url: str):
    """Sync connection for both engines (alembic's own URL form is sync)."""
    return create_engine(url, pool_pre_ping=True)


@pytest.fixture
def migration_url():
    """A database each migration test owns end to end.

    SQLite: a throwaway file. PostgreSQL (CI): a scratch database that is reset to
    `base` before and after, so the suite is repeatable on one instance."""
    url = _scratch_url()
    if _is_postgres(url):
        cfg = get_alembic_config(url)
        command.downgrade(cfg, "base")
        yield url
        command.downgrade(cfg, "base")
        return
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        path = tmp.name
    try:
        yield f"sqlite:///{path}"
    finally:
        if os.path.exists(path):
            os.remove(path)


@pytest.fixture
def legacy_migration_url():
    """Target for the apps/api lineage. alembic/env.py resolves its URL from
    globaltalk settings, so the scratch database is steered through the same
    environment variable the app uses."""
    url = _scratch_url("LEGACY_TEST_DATABASE_URL")
    previous = os.environ.get("GLOBALTALK_DATABASE_URL")
    if _is_postgres(url):
        os.environ["GLOBALTALK_DATABASE_URL"] = url
        cfg = get_legacy_alembic_config(url)
        command.downgrade(cfg, "base")
        try:
            yield url
        finally:
            command.downgrade(cfg, "base")
            if previous is None:
                os.environ.pop("GLOBALTALK_DATABASE_URL", None)
            else:
                os.environ["GLOBALTALK_DATABASE_URL"] = previous
        return
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        path = tmp.name
    os.environ["GLOBALTALK_DATABASE_URL"] = f"sqlite:///{path}"
    try:
        yield f"sqlite:///{path}"
    finally:
        if previous is None:
            os.environ.pop("GLOBALTALK_DATABASE_URL", None)
        else:
            os.environ["GLOBALTALK_DATABASE_URL"] = previous
        if os.path.exists(path):
            os.remove(path)



@pytest.mark.asyncio
async def test_fresh_database_alembic_upgrade_and_drift_check(migration_url):
    """Verify alembic upgrade head builds all tables cleanly from zero with no drift."""
    cfg = get_alembic_config(migration_url)

    # 1. Upgrade from scratch to head
    await asyncio.to_thread(command.upgrade, cfg, "head")

    # 2. Inspect what the pipeline actually produced
    eng = _connect(migration_url)
    try:
        with eng.connect() as conn:
            tables = set(inspect(conn).get_table_names())

            # Key production tables must all be present
            required_tables = {
                "users",
                "organizations",
                "organization_members",
                "user_identities",
                "phone_numbers",
                "call_sessions",
                "call_events",
                "agent_prompts",
                "prompt_versions",
                "language_capabilities",
                "language_pair_capabilities",
                "translation_segments",
                "transcript_segments",
                "meetings",
                "webhook_endpoints",
                "webhook_deliveries",
                "usage_records",
                "subscriptions",
                "billing_events",
                "audit_logs",
                "alembic_version",
            }
            missing = required_tables - tables
            assert not missing, f"Missing tables after alembic upgrade head: {missing}"

            # The revision the pipeline just landed on is the revision the production
            # boot gate expects. A hardcoded EXPECTED_HEAD literal could never promise
            # this: the gate and the script directory are read from one source.
            current_rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
            assert current_rev == _migration_head_revision()

            l_cols = {c["name"] for c in inspect(conn).get_columns("language_capabilities")}
            assert "speech_input_supported" in l_cols
            assert "realtime_supported" in l_cols
            assert "stt_status" in l_cols
    finally:
        eng.dispose()

    # 3. Verify Alembic check detects no drift
    await asyncio.to_thread(command.check, cfg)


@pytest.mark.asyncio
async def test_migration_downgrade_and_reupgrade_cycle(migration_url):
    """Verify rollback (downgrade -1) and re-upgrade execute reliably."""
    cfg = get_alembic_config(migration_url)
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()
    previous = script.get_revision(head).down_revision

    # Upgrade to head
    await asyncio.to_thread(command.upgrade, cfg, "head")

    # Downgrade one revision (apps/api keeps more than two, so name the parent)
    await asyncio.to_thread(command.downgrade, cfg, previous)

    eng = _connect(migration_url)
    try:
        with eng.connect() as conn:
            assert conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none() == previous
            tables = set(inspect(conn).get_table_names())
        assert "user_identities" not in tables
        assert "phone_numbers" not in tables
    finally:
        eng.dispose()

    # Re-upgrade to head
    await asyncio.to_thread(command.upgrade, cfg, "head")

    eng = _connect(migration_url)
    try:
        with eng.connect() as conn:
            assert conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none() == head
            tables = set(inspect(conn).get_table_names())
        assert "user_identities" in tables
        assert "phone_numbers" in tables
    finally:
        eng.dispose()



@pytest.mark.asyncio
async def test_production_fails_closed_when_schema_unmigrated(monkeypatch):
    """Production mode must reject booting if database migrations are missing or outdated."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        async_url = f"sqlite+aiosqlite:///{db_path}"
        test_engine = create_async_engine(async_url)

        head = _migration_head_revision()
        previous = ScriptDirectory.from_config(
            get_alembic_config(async_url)
        ).get_revision(head).down_revision

        # Mock production settings and engine
        monkeypatch.setattr(settings, "app_env", "production")
        from app.db import session as sess_module
        monkeypatch.setattr(sess_module, "engine", lambda: test_engine)

        # 1. Uninitialized database -> must fail
        with pytest.raises(RuntimeError, match="Database schema uninitialized"):
            await _ensure_schema()

        # 2. Database with an outdated revision -> must fail, naming the head it wants
        async with test_engine.begin() as conn:
            await conn.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
            await conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
            await conn.execute(text("INSERT INTO alembic_version VALUES (:rev)"), {"rev": previous})

        with pytest.raises(RuntimeError, match=f"expected '{head}'"):
            await _ensure_schema()

        # 3. Database matching the migration head -> must succeed cleanly
        async with test_engine.begin() as conn:
            await conn.execute(
                text("UPDATE alembic_version SET version_num = :rev"), {"rev": head}
            )

        # Should not raise any error
        await _ensure_schema()

        # 4. A revision the script directory does not know about (a partially applied
        # or hand-edited schema) is not "close enough" — it fails closed too.
        async with test_engine.begin() as conn:
            await conn.execute(
                text("UPDATE alembic_version SET version_num = 'not_a_revision'")
            )
        with pytest.raises(RuntimeError, match="Database migration version mismatch"):
            await _ensure_schema()

        await test_engine.dispose()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_user_identity_cascades_and_constraints(services_app_client):
    """Verify UserIdentity relational foreign key cascade and unique constraints."""
    async with db_session() as db:
        # Create user
        uid = uuid.uuid4()
        user = User(
            id=uid,
            email=f"ident_{uid.hex[:8]}@example.com",
            password_hash="hashed",
            name="OAuth Tester",
        )
        db.add(user)
        await db.flush()

        # Add OAuth Identity
        ident = UserIdentity(
            user_id=user.id,
            provider="google",
            provider_user_id="google-sub-12345",
            email=user.email,
            email_verified=True,
            profile_data={"sub": "google-sub-12345"},
        )
        db.add(ident)
        await db.commit()

        # Duplicate (provider, provider_user_id) must be rejected
        ident_dup = UserIdentity(
            user_id=user.id,
            provider="google",
            provider_user_id="google-sub-12345",
            email="other@example.com",
        )
        db.add(ident_dup)
        with pytest.raises(Exception):
            await db.commit()
        await db.rollback()

        # Deleting user should cascade delete user_identity
        user_to_delete = await db.get(User, uid)
        await db.delete(user_to_delete)
        await db.commit()

        remaining_ident = (
            await db.execute(
                text("SELECT count(*) FROM user_identities WHERE user_id = :uid"),
                {"uid": str(uid)},
            )
        ).scalar()
        assert remaining_ident == 0



@pytest.mark.asyncio
async def test_legacy_lineage_migrations_cover_their_own_models(legacy_migration_url):
    """apps/api is a second Alembic lineage against the same ORM it boots.

    Its revisions used to be incomplete: the columns its `init_db()` ALTER-ed in at
    dev boot were missing from `alembic upgrade head`, and production
    (DB_AUTOCREATE=false) skipped that patching entirely — so a migrated apps/api
    database did not match the models its workers use."""
    cfg = get_legacy_alembic_config(legacy_migration_url)
    await asyncio.to_thread(command.upgrade, cfg, "head")

    eng = _connect(legacy_migration_url)
    try:
        with eng.connect() as conn:
            webhook_cols = {c["name"] for c in inspect(conn).get_columns("webhook_deliveries")}
            lang_cols = {c["name"] for c in inspect(conn).get_columns("language_capabilities")}
    finally:
        eng.dispose()

    # Every column the runtime patcher used to invent is now migration-owned.
    assert {"endpoint_id", "payload_json", "last_status_code", "next_retry_at"} <= webhook_cols
    assert {"script", "rtl", "translation_status", "realtime_status", "stt_status"} <= lang_cols

    # Completeness, proven the way Alembic does it: model vs. migrated schema is empty diff.
    await asyncio.to_thread(command.check, cfg)


@pytest.mark.asyncio
async def test_legacy_lineage_cannot_move_the_api_migration_gate(migration_url, monkeypatch):
    """One database, two lineages: apps/api must never rewrite `alembic_version`.

    Deployment gives both processes the same DATABASE_URL. If the legacy lineage
    recorded its revision in the API's version table, the production boot gate
    would read a revision it cannot resolve and every API replica would fail to
    start — or, worse, an operator would "fix" it by stamping over real schema."""
    api_cfg = get_alembic_config(migration_url)
    await asyncio.to_thread(command.upgrade, api_cfg, "head")
    head = _migration_head_revision()

    # apps/api's env.py resolves its URL through globaltalk.core.db.database_url()
    monkeypatch.setenv("GLOBALTALK_DATABASE_URL", migration_url)
    legacy_cfg = get_legacy_alembic_config(migration_url)
    await asyncio.to_thread(command.stamp, legacy_cfg, "head")

    eng = _connect(migration_url)
    try:
        with eng.connect() as conn:
            tables = set(inspect(conn).get_table_names())
            assert LEGACY_VERSION_TABLE in tables
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none() == head
            legacy_rev = conn.execute(
                text(f"SELECT version_num FROM {LEGACY_VERSION_TABLE}")
            ).scalar_one_or_none()
        assert legacy_rev and legacy_rev != head
    finally:
        eng.dispose()

    # The API gate is unaffected: it still sees its own head and boots.
    from app.db import session as sess_module
    async_engine = create_async_engine(
        migration_url.replace("postgresql+psycopg", "postgresql+asyncpg")
        if migration_url.startswith("postgresql")
        else migration_url.replace("sqlite:///", "sqlite+aiosqlite:///")
    )
    try:
        monkeypatch.setattr(settings, "app_env", "production")
        monkeypatch.setattr(sess_module, "engine", lambda: async_engine)
        await _ensure_schema()
    finally:
        await async_engine.dispose()


@pytest.mark.asyncio
async def test_legacy_production_boot_fails_closed_instead_of_patching(legacy_migration_url, monkeypatch):
    """apps/api in production must refuse an unmigrated database, not reshape it."""
    import globaltalk.core.db as legacy_db

    eng = _connect(legacy_migration_url)
    monkeypatch.setattr(legacy_db, "engine", eng)
    monkeypatch.setattr(type(legacy_db.settings), "is_production", property(lambda self: True))

    try:
        with pytest.raises(RuntimeError, match="uninitialized"):
            legacy_db.init_db()
        # Nothing was quietly created: refusing to boot is not the same as patching.
        assert "users" not in set(inspect(eng).get_table_names())

        await asyncio.to_thread(command.upgrade, get_legacy_alembic_config(legacy_migration_url), "head")
        legacy_db.init_db()  # migrated to head -> boots

        # A stale (rolled-back) database fails closed too.
        with eng.begin() as conn:
            conn.execute(
                text(f"UPDATE {LEGACY_VERSION_TABLE} SET version_num = 'e7150a82b3d1'")
            )
        with pytest.raises(RuntimeError, match="version mismatch"):
            legacy_db.init_db()
    finally:
        eng.dispose()


def test_legacy_runtime_schema_patching_is_gone():
    """No raw ALTER TABLE at boot: dev convenience is create_all, production is Alembic."""
    import globaltalk.core.db as legacy_db

    assert not hasattr(legacy_db, "_ensure_columns")
