"""Audit service — immutable security/business event log (PDD §20)."""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import context
from app.db import models as M
from app.db.base import utcnow

log = logging.getLogger("app.audit")


async def record(
    db: AsyncSession, *, action: str, org_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None, actor_kind: str = "user",
    resource_type: str = "", resource_id: str = "", outcome: str = "success",
    details: dict | None = None, ip_hash: str = "",
) -> M.AuditLog:
    ctx = context.current()
    entry = M.AuditLog(
        org_id=org_id, actor_id=actor_id, actor_kind=actor_kind,
        action=action, resource_type=resource_type, resource_id=str(resource_id),
        ip_hash=ip_hash, request_id=ctx.request_id, outcome=outcome,
        details_json=details or {}, created_at=utcnow(),
    )
    db.add(entry)
    log.info("audit %s actor=%s resource=%s/%s outcome=%s",
             action, actor_kind, resource_type, resource_id, outcome)
    return entry


async def list_events(db: AsyncSession, org_id: uuid.UUID | None, *,
                      action: str | None = None, limit: int = 100,
                      offset: int = 0, since_days: int | None = None):
    q = select(M.AuditLog).order_by(M.AuditLog.created_at.desc())
    if org_id is not None:
        q = q.where(M.AuditLog.org_id == org_id)
    if action:
        q = q.where(M.AuditLog.action == action)
    if since_days:
        q = q.where(M.AuditLog.created_at >= utcnow() - timedelta(days=since_days))
    res = await db.execute(q.limit(limit).offset(offset))
    return res.scalars().all()
