"""Phase 7: Database Models & Alembic Migrations Hardening Test Suite.

Verifies:
1. Complete Alembic upgrade pipeline on fresh database without schema drift.
2. Clean downgrade/rollback and re-upgrade execution.
3. Production fail-closed enforcement when migrations are unapplied or version mismatched.
4. Tenancy & foreign key integrity (cascades, unique constraints).
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from pathlib import Path
import pytest
from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import create_async_engine

from alembic.config import Config
from alembic import command

from app.config import settings
from app.db.base import Base
from app.db.models import User, Organization, OrganizationMember, UserIdentity, PhoneNumber
from app.db.session import init_db, db_session
from app.main import _ensure_schema


REPO_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI_PATH = str(REPO_ROOT / "services" / "api" / "alembic.ini")


def get_alembic_config(db_url: str) -> Config:
    cfg = Config(ALEMBIC_INI_PATH)
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


@pytest.mark.asyncio
async def test_fresh_database_alembic_upgrade_and_drift_check():
    """Verify alembic upgrade head builds all tables cleanly from zero with no drift."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        sync_url = f"sqlite:///{db_path}"
        async_url = f"sqlite+aiosqlite:///{db_path}"

        cfg = get_alembic_config(sync_url)

        # 1. Upgrade from scratch to head
        await asyncio.to_thread(command.upgrade, cfg, "head")

        # 2. Inspect created tables
        engine = create_async_engine(async_url)
        async with engine.connect() as conn:
            tables = await conn.run_sync(lambda sync_conn: set(inspect(sync_conn).get_table_names()))
            
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

            # Check head version in database
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            current_rev = result.scalar_one_or_none()
            assert current_rev == "2202ca7dc080"

            # Check new columns in language_capabilities
            l_cols = await conn.run_sync(
                lambda sync_conn: {c["name"] for c in inspect(sync_conn).get_columns("language_capabilities")}
            )
            assert "speech_input_supported" in l_cols
            assert "realtime_supported" in l_cols
            assert "stt_status" in l_cols

        await engine.dispose()

        # 3. Verify Alembic check detects no drift
        await asyncio.to_thread(command.check, cfg)

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_migration_downgrade_and_reupgrade_cycle():
    """Verify rollback (downgrade -1) and re-upgrade execute reliably."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        sync_url = f"sqlite:///{db_path}"
        async_url = f"sqlite+aiosqlite:///{db_path}"
        cfg = get_alembic_config(sync_url)

        # Upgrade to head
        await asyncio.to_thread(command.upgrade, cfg, "head")

        # Downgrade 1 revision back to initial schema (eae02319e4b2)
        await asyncio.to_thread(command.downgrade, cfg, "-1")

        engine = create_async_engine(async_url)
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            assert result.scalar_one_or_none() == "eae02319e4b2"
            
            tables = await conn.run_sync(lambda sync_conn: set(inspect(sync_conn).get_table_names()))
            assert "user_identities" not in tables
            assert "phone_numbers" not in tables

        await engine.dispose()

        # Re-upgrade to head
        await asyncio.to_thread(command.upgrade, cfg, "head")

        engine = create_async_engine(async_url)
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            assert result.scalar_one_or_none() == "2202ca7dc080"
            tables = await conn.run_sync(lambda sync_conn: set(inspect(sync_conn).get_table_names()))
            assert "user_identities" in tables
            assert "phone_numbers" in tables

        await engine.dispose()

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.mark.asyncio
async def test_production_fails_closed_when_schema_unmigrated(monkeypatch):
    """Production mode must reject booting if database migrations are missing or outdated."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        async_url = f"sqlite+aiosqlite:///{db_path}"
        test_engine = create_async_engine(async_url)

        # Mock production settings and engine
        monkeypatch.setattr(settings, "app_env", "production")
        from app.db import session as sess_module
        monkeypatch.setattr(sess_module, "engine", lambda: test_engine)

        # 1. Uninitialized database -> must fail
        with pytest.raises(RuntimeError, match="Database schema uninitialized"):
            await _ensure_schema()

        # 2. Database with outdated revision -> must fail
        async with test_engine.begin() as conn:
            await conn.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
            await conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
            await conn.execute(text("INSERT INTO alembic_version VALUES ('eae02319e4b2')"))

        with pytest.raises(RuntimeError, match="Database migration version mismatch in production"):
            await _ensure_schema()

        # 3. Database matching expected head -> must succeed cleanly
        async with test_engine.begin() as conn:
            await conn.execute(text("UPDATE alembic_version SET version_num = '2202ca7dc080'"))

        # Should not raise any error
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

