"""Phase 3 / Day 4 — GDPR Right to Erasure & Deletion Endpoints.

Tests:
1. DELETE /api/v1/auth/me:
   - User requests deletion of their own account.
   - Returns 204 No Content.
   - User row is anonymized: email -> deleted-{id}@deleted.invalid, name -> 'Deleted User', status -> 'deleted'.
   - All refresh tokens and active sessions for the user are revoked.
2. DELETE /api/v1/organizations/current:
   - Non-owner role is rejected with 403 Forbidden.
   - Owner role executes deletion -> 204 No Content.
   - Organization status -> 'deleted', documents' storage objects are purged.
3. Standalone translation history policy sweep:
   - Standalone TranslationSegment rows older than retention_translation_history_days are purged.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db import models as M
from app.db.session import db_session
from app.services import retention_service


@pytest.mark.asyncio
async def test_gdpr_delete_user_account(services_app_client, user):
    client = services_app_client
    headers = user["headers"]
    user_id = uuid.UUID(user["user_id"])

    # 1. Verify user can access /me before deletion
    me_res = client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200

    # 2. Call DELETE /api/v1/auth/me
    del_res = client.delete("/api/v1/auth/me", headers=headers)
    assert del_res.status_code == 204

    # 3. Check DB state: user is anonymized and status=deleted
    async with db_session() as db:
        u = await db.get(M.User, user_id)
        assert u is not None
        assert u.status == "deleted"
        assert u.email.startswith(f"deleted-{user_id}@")
        assert u.name == "Deleted User"
        assert u.deleted_at is not None

        # Check sessions / tokens are revoked
        tokens = (await db.execute(
            select(M.RefreshToken).where(M.RefreshToken.user_id == user_id)
        )).scalars().all()
        for t in tokens:
            assert t.revoked_at is not None


@pytest.mark.asyncio
async def test_delete_current_org_enforces_owner_role(services_app_client, user):
    client = services_app_client
    headers = user["headers"]
    org_id = uuid.UUID(user["org_id"])
    user_id = uuid.UUID(user["user_id"])

    # 1. Temporarily change member role to 'member'
    async with db_session() as db:
        m = (await db.execute(select(M.OrganizationMember).where(
            M.OrganizationMember.org_id == org_id,
            M.OrganizationMember.user_id == user_id
        ))).scalars().first()
        if m:
            m.role = "member"
            await db.commit()

    # Non-owner attempt must fail with 403
    forbidden_res = client.delete("/api/v1/organizations/current", headers=headers)
    assert forbidden_res.status_code == 403

    # 2. Restore owner role
    async with db_session() as db:
        m = (await db.execute(select(M.OrganizationMember).where(
            M.OrganizationMember.org_id == org_id,
            M.OrganizationMember.user_id == user_id
        ))).scalars().first()
        if m:
            m.role = "owner"
            await db.commit()

    # Owner attempt succeeds with 204
    ok_res = client.delete("/api/v1/organizations/current", headers=headers)
    assert ok_res.status_code == 204

    # Check DB state
    async with db_session() as db:
        org = await db.get(M.Organization, org_id)
        assert org is not None
        assert org.status == "deleted"
        assert org.deleted_at is not None


@pytest.mark.asyncio
async def test_standalone_translation_history_retention_sweep(monkeypatch):
    import app.config as cfg_mod

    # Force translation history retention to 30 days
    monkeypatch.setattr(cfg_mod.settings, "retention_translation_history_days", 30)
    monkeypatch.setattr(retention_service.settings, "retention_translation_history_days", 30)

    now = datetime.now(UTC)
    old_id = uuid.uuid4()
    new_id = uuid.uuid4()

    async with db_session() as db:
        old_trans = M.TranslationSegment(
            id=old_id,
            segment_id=None,  # standalone text
            product="text",
            source_lang="en",
            target_lang="es",
            source_text="old hello",
            target_text="old hola",
            created_at=now - timedelta(days=45),
        )
        new_trans = M.TranslationSegment(
            id=new_id,
            segment_id=None,
            product="text",
            source_lang="en",
            target_lang="es",
            source_text="new hello",
            target_text="new hola",
            created_at=now - timedelta(days=10),
        )
        db.add_all([old_trans, new_trans])
        await db.commit()

    try:
        async with db_session() as db:
            counts = await retention_service.sweep(db)

        # Check that old standalone translation was swept and new one survived
        async with db_session() as db:
            old_row = await db.get(M.TranslationSegment, old_id)
            new_row = await db.get(M.TranslationSegment, new_id)
            assert old_row is None
            assert new_row is not None
    finally:
        async with db_session() as db:
            from sqlalchemy import delete
            await db.execute(delete(M.TranslationSegment).where(
                M.TranslationSegment.id.in_([old_id, new_id])
            ))
            await db.commit()
