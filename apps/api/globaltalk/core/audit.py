"""Audit logging + usage metering (immutable events)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from globaltalk.core.logging import get_logger, request_id_var
from globaltalk.models import AuditLog, UsageRecord

log = get_logger("audit")


def audit(db: Session, action: str, *, org_id: str | None = None, actor_user_id: str | None = None,
          actor_api_key_id: str | None = None, resource_type: str = "", resource_id: str = "",
          ip_address: str = "", details: dict[str, Any] | None = None, commit: bool = True) -> None:
    entry = AuditLog(
        org_id=org_id, actor_user_id=actor_user_id, actor_api_key_id=actor_api_key_id,
        action=action, resource_type=resource_type, resource_id=resource_id,
        ip_address=ip_address, request_id=request_id_var.get(), details=details or {})
    db.add(entry)
    if commit:
        db.commit()
    else:
        db.flush()


def meter(db: Session, *, org_id: str, dimension: str, quantity: float,
          user_id: str | None = None, api_key_id: str | None = None,
          meeting_id: str | None = None, document_id: str | None = None,
          metadata: dict[str, Any] | None = None, commit: bool = False) -> UsageRecord:
    """Append an immutable usage event. Billing aggregates these; never measures directly."""
    rec = UsageRecord(org_id=org_id, user_id=user_id, api_key_id=api_key_id, dimension=dimension,
                      quantity=quantity, meeting_id=meeting_id, document_id=document_id,
                      metadata_=metadata or {})
    db.add(rec)
    if commit:
        db.commit()
    else:
        db.flush()
    return rec


def usage_summary(db: Session, org_id: str, since: datetime | None = None) -> dict[str, float]:
    q = db.query(UsageRecord.dimension, UsageRecord.quantity).filter(UsageRecord.org_id == org_id)
    if since:
        q = q.filter(UsageRecord.created_at >= since)
    totals: dict[str, float] = {}
    for dim, qty in q.all():
        totals[dim] = totals.get(dim, 0.0) + float(qty)
    return totals
