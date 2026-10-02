"""Platform routers: API keys, usage, billing, webhooks, search, feedback,
feature flags, integrations, admin dashboard (PDD §28-§30, §47-§50)."""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache
from app.config import settings
from app.db import models as M
from app.db.base import utcnow
from app.db.session import get_db
from app.deps import Principal, get_principal, require_org_user
from app.errors import AuthorizationError, NotFoundError, ValidationError
from app.schemas import (
    ApiKeyCreate, ApiKeyCreated, ApiKeyOut, AuditLogOut, BillingEventOut,
    FeedbackIn, SearchResponse, SubscriptionOut, UsageSummary, WebhookCreate,
    WebhookOut,
)
from app.security import generate_api_key
from app.services import audit_service, billing_service, usage_service, webhook_service

log = logging.getLogger("app.routers.platform")

keys_router = APIRouter(prefix="/api/v1/api-keys", tags=["api-keys"])
usage_router = APIRouter(prefix="/api/v1", tags=["usage"])
webhooks_router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])
search_router = APIRouter(prefix="/api/v1/search", tags=["search"])
feedback_router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])
flags_router = APIRouter(prefix="/api/v1/flags", tags=["feature-flags"])
integrations_router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])
admin_router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# --------------------------------------------------------------------------- #
# API keys
# --------------------------------------------------------------------------- #

@keys_router.post("", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(body: ApiKeyCreate,
                         principal: Principal = Depends(require_org_user),
                         db: AsyncSession = Depends(get_db)):
    principal.require("manage_api_keys")
    plaintext, key_hash, prefix = generate_api_key()
    expires = (utcnow() + timedelta(days=body.expires_in_days)
               if body.expires_in_days else None)
    key = M.ApiKey(org_id=principal.org_id, created_by=principal.user_id,
                   name=body.name, key_hash=key_hash, prefix=prefix,
                   scopes=body.scopes, expires_at=expires)
    db.add(key)
    await audit_service.record(db, action="api_key.created", org_id=principal.org_id,
                               actor_id=principal.user_id, resource_type="api_key",
                               resource_id=prefix)
    await db.commit()
    out = ApiKeyCreated(**ApiKeyOut.model_validate(key).model_dump(),
                        plaintext_key=plaintext)  # shown exactly once, never stored
    return out


@keys_router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(principal: Principal = Depends(require_org_user),
                        db: AsyncSession = Depends(get_db)):
    principal.require("manage_api_keys")
    res = await db.execute(select(M.ApiKey).where(
        M.ApiKey.org_id == principal.org_id)
        .order_by(M.ApiKey.created_at.desc()))
    return [ApiKeyOut.model_validate(k) for k in res.scalars().all()]


async def _key(db, key_id, principal) -> M.ApiKey:
    k = await db.get(M.ApiKey, key_id)
    if k is None or k.org_id != principal.org_id:
        raise NotFoundError("API key not found.")
    return k


@keys_router.post("/{key_id}/rotate", response_model=ApiKeyCreated)
async def rotate_api_key(key_id: uuid.UUID,
                         principal: Principal = Depends(require_org_user),
                         db: AsyncSession = Depends(get_db)):
    principal.require("manage_api_keys")
    old = await _key(db, key_id, principal)
    old.status = "revoked"
    old.revoked_at = utcnow()
    plaintext, key_hash, prefix = generate_api_key()
    new = M.ApiKey(org_id=principal.org_id, created_by=principal.user_id,
                   name=old.name, key_hash=key_hash, prefix=prefix,
                   scopes=old.scopes, expires_at=old.expires_at)
    db.add(new)
    await audit_service.record(db, action="api_key.rotated", org_id=principal.org_id,
                               actor_id=principal.user_id, resource_type="api_key",
                               resource_id=prefix, details={"old": old.prefix})
    await db.commit()
    await webhook_service.dispatch(db, principal.org_id, "api_key.revoked",
                                   {"prefix": old.prefix, "reason": "rotated"})
    out = ApiKeyCreated(**ApiKeyOut.model_validate(new).model_dump(),
                        plaintext_key=plaintext)
    return out


@keys_router.post("/{key_id}/revoke", status_code=204)
async def revoke_api_key(key_id: uuid.UUID,
                         principal: Principal = Depends(require_org_user),
                         db: AsyncSession = Depends(get_db)):
    principal.require("manage_api_keys")
    k = await _key(db, key_id, principal)
    k.status = "revoked"
    k.revoked_at = utcnow()
    await audit_service.record(db, action="api_key.revoked", org_id=principal.org_id,
                               actor_id=principal.user_id, resource_type="api_key",
                               resource_id=k.prefix)
    await db.commit()
    await webhook_service.dispatch(db, principal.org_id, "api_key.revoked",
                                   {"prefix": k.prefix, "reason": "manual"})


# --------------------------------------------------------------------------- #
# Usage & billing
# --------------------------------------------------------------------------- #

@usage_router.get("/usage", response_model=UsageSummary)
async def get_usage(principal: Principal = Depends(require_org_user),
                    db: AsyncSession = Depends(get_db),
                    days: int = Query(default=30, le=365)):
    principal.require("view_usage")
    data = await usage_service.usage_summary(db, principal.org_id, days)
    return UsageSummary(**data)


@usage_router.get("/usage/quota", response_model=dict)
async def get_quota(principal: Principal = Depends(require_org_user),
                    db: AsyncSession = Depends(get_db)):
    used = await usage_service.current_period_usage(db, principal.org_id)
    sub = (await db.execute(select(M.Subscription).where(
        M.Subscription.org_id == principal.org_id))).scalars().first()
    quotas = (sub.quota_json if sub else None) or \
        usage_service.DEFAULT_PLAN_QUOTAS.get(sub.plan_code if sub else "free",
                                              usage_service.DEFAULT_PLAN_QUOTAS["free"])
    return {"plan": sub.plan_code if sub else "free", "used": used,
            "quota": {k: (None if v == float("inf") else v) for k, v in quotas.items()}}


@usage_router.get("/billing/subscription", response_model=SubscriptionOut)
async def get_subscription(principal: Principal = Depends(require_org_user),
                           db: AsyncSession = Depends(get_db)):
    sub = await billing_service.get_or_create_subscription(db, principal.org)
    return SubscriptionOut.model_validate(sub)


class PlanChange(BaseModel):
    plan: str


@usage_router.post("/billing/subscription", response_model=SubscriptionOut)
async def change_subscription(body: PlanChange,
                              principal: Principal = Depends(require_org_user),
                              db: AsyncSession = Depends(get_db)):
    principal.require("manage_billing")
    sub = await billing_service.change_plan(db, principal.org, body.plan,
                                            principal.user_id)
    return SubscriptionOut.model_validate(sub)


@usage_router.get("/billing/events", response_model=list[BillingEventOut])
async def billing_events(principal: Principal = Depends(require_org_user),
                         db: AsyncSession = Depends(get_db)):
    principal.require("manage_billing")
    events = await billing_service.list_events(db, principal.org_id)
    return [BillingEventOut.model_validate(e) for e in events]


@usage_router.get("/billing/preview-invoice", response_model=dict)
async def preview_invoice(principal: Principal = Depends(require_org_user),
                          db: AsyncSession = Depends(get_db)):
    principal.require("manage_billing")
    now = utcnow()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return await billing_service.compute_invoice(db, principal.org_id, start, now)


# --------------------------------------------------------------------------- #
# Webhooks
# --------------------------------------------------------------------------- #

@webhooks_router.post("", response_model=WebhookOut, status_code=201)
async def create_webhook(body: WebhookCreate,
                         principal: Principal = Depends(require_org_user),
                         db: AsyncSession = Depends(get_db)):
    principal.require("manage_webhooks")
    ep = await webhook_service.register_endpoint(db, principal.org_id, body.url,
                                                 body.events, principal.user_id)
    out = WebhookOut.model_validate(ep)
    return out


@webhooks_router.get("", response_model=list[WebhookOut])
async def list_webhooks(principal: Principal = Depends(require_org_user),
                        db: AsyncSession = Depends(get_db)):
    principal.require("manage_webhooks")
    res = await db.execute(select(M.WebhookEndpoint).where(
        M.WebhookEndpoint.org_id == principal.org_id))
    return [WebhookOut.model_validate(e) for e in res.scalars().all()]


@webhooks_router.get("/{ep_id}/secret", response_model=dict)
async def webhook_secret(ep_id: uuid.UUID,
                         principal: Principal = Depends(require_org_user),
                         db: AsyncSession = Depends(get_db)):
    """Reveal signing secret (permission-gated, audited)."""
    principal.require("manage_webhooks")
    ep = await db.get(M.WebhookEndpoint, ep_id)
    if ep is None or ep.org_id != principal.org_id:
        raise NotFoundError("Webhook not found.")
    await audit_service.record(db, action="webhook.secret_viewed",
                               org_id=principal.org_id, actor_id=principal.user_id,
                               resource_type="webhook", resource_id=str(ep_id))
    await db.commit()
    return {"secret": ep.secret}


@webhooks_router.delete("/{ep_id}", status_code=204)
async def delete_webhook(ep_id: uuid.UUID,
                         principal: Principal = Depends(require_org_user),
                         db: AsyncSession = Depends(get_db)):
    principal.require("manage_webhooks")
    ep = await db.get(M.WebhookEndpoint, ep_id)
    if ep is None or ep.org_id != principal.org_id:
        raise NotFoundError("Webhook not found.")
    ep.status = "deleted"
    await db.commit()


@webhooks_router.get("/{ep_id}/deliveries", response_model=list[dict])
async def webhook_deliveries(ep_id: uuid.UUID,
                             principal: Principal = Depends(require_org_user),
                             db: AsyncSession = Depends(get_db)):
    ep = await db.get(M.WebhookEndpoint, ep_id)
    if ep is None or ep.org_id != principal.org_id:
        raise NotFoundError("Webhook not found.")
    res = await db.execute(select(M.WebhookDelivery).where(
        M.WebhookDelivery.endpoint_id == ep_id)
        .order_by(M.WebhookDelivery.created_at.desc()).limit(50))
    return [{"id": str(d.id), "event": d.event_type, "status": d.status,
             "attempts": d.attempts, "last_status_code": d.last_status_code,
             "created_at": d.created_at.isoformat()} for d in res.scalars().all()]


@webhooks_router.get("/meta/events", response_model=list[str])
async def webhook_event_types():
    return webhook_service.EVENT_TYPES


# --------------------------------------------------------------------------- #
# Search / feedback / flags / integrations
# --------------------------------------------------------------------------- #

@search_router.get("", response_model=SearchResponse)
async def search(q: str = Query(min_length=1, max_length=200),
                 principal: Principal = Depends(require_org_user),
                 db: AsyncSession = Depends(get_db)):
    from app.services import search_service
    result = await search_service.search_all(db, principal.org_id, q)
    return SearchResponse(query=q, **result)


@feedback_router.post("", status_code=201)
async def submit_feedback(body: FeedbackIn,
                          principal: Principal = Depends(get_principal),
                          db: AsyncSession = Depends(get_db)):
    fb = M.Feedback(org_id=principal.org_id, user_id=principal.user_id,
                    target_type=body.target_type, target_id=body.target_id,
                    rating=body.rating, correction_text=body.correction_text,
                    comment=body.comment, source_lang=body.source_lang,
                    target_lang=body.target_lang)
    db.add(fb)
    await db.commit()
    return {"status": "recorded"}


@flags_router.get("", response_model=dict)
async def get_flags(principal: Principal = Depends(get_principal),
                    db: AsyncSession = Depends(get_db)):
    from app.deps import flag_enabled
    keys = ["voice_translation", "document_translation", "agent_bridge",
            "voice_preservation", "new_translation_model",
            "experimental_language", "enterprise_sso"]
    return {k: await flag_enabled(db, k, principal.org_id) for k in keys}


class IntegrationCreate(BaseModel):
    kind: str = Field(pattern="^(zoom|teams|google_meet|slack|crm|helpdesk|cms|webhook|mcp)$")
    name: str = ""
    config: dict = Field(default_factory=dict)


@integrations_router.get("", response_model=list[dict])
async def list_integrations(principal: Principal = Depends(require_org_user),
                            db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(M.Integration).where(
        M.Integration.org_id == principal.org_id))
    return [{"id": str(i.id), "kind": i.kind, "name": i.name, "status": i.status,
             "config": i.config_json, "created_at": i.created_at.isoformat()}
            for i in res.scalars().all()]


@integrations_router.post("", status_code=201, response_model=dict)
async def create_integration(body: IntegrationCreate,
                             principal: Principal = Depends(require_org_user),
                             db: AsyncSession = Depends(get_db)):
    """Architecture-ready integration registry (PDD §48).

    Connectors are modular: registration + credential-reference storage is
    implemented; each connector's sync logic plugs into the same record.
    Credentials themselves NEVER live in this DB — only secret-manager refs.
    """
    principal.require("manage_integrations")
    i = M.Integration(org_id=principal.org_id, kind=body.kind,
                      name=body.name or body.kind, status="registered",
                      config_json=body.config)
    db.add(i)
    await audit_service.record(db, action="integration.registered",
                               org_id=principal.org_id, actor_id=principal.user_id,
                               resource_type="integration", resource_id=body.kind)
    await db.commit()
    return {"id": str(i.id), "kind": i.kind, "status": i.status}


@integrations_router.delete("/{integration_id}", status_code=204)
async def delete_integration(integration_id: uuid.UUID,
                             principal: Principal = Depends(require_org_user),
                             db: AsyncSession = Depends(get_db)):
    principal.require("manage_integrations")
    i = await db.get(M.Integration, integration_id)
    if i is None or i.org_id != principal.org_id:
        raise NotFoundError("Integration not found.")
    await db.delete(i)
    await db.commit()


# --------------------------------------------------------------------------- #
# Admin (platform admins only)
# --------------------------------------------------------------------------- #

def _require_platform_admin(principal: Principal = Depends(get_principal)) -> Principal:
    if not (principal.user and principal.user.is_platform_admin):
        raise AuthorizationError("Platform administrator access required.")
    return principal


@admin_router.get("/overview", response_model=dict)
async def admin_overview(principal: Principal = Depends(_require_platform_admin),
                         db: AsyncSession = Depends(get_db)):
    from app import metrics as met
    users = (await db.execute(select(func.count(M.User.id)))).scalar() or 0
    orgs = (await db.execute(select(func.count(M.Organization.id)))).scalar() or 0
    meetings = (await db.execute(select(func.count(M.Meeting.id)))).scalar() or 0
    live_meetings = (await db.execute(select(func.count(M.Meeting.id)).where(
        M.Meeting.status == "live"))).scalar() or 0
    docs = (await db.execute(select(func.count(M.Document.id)))).scalar() or 0
    failed_docs = (await db.execute(select(func.count(M.Document.id)).where(
        M.Document.status == "failed"))).scalar() or 0
    from app.queue import queue
    depths = {}
    for q in ("default", "documents", "webhooks"):
        depths[q] = await queue().depth(q)
    ai_health = await __import__("app.ai", fromlist=["ai"]).ai.health()
    from prometheus_client import REGISTRY
    def gauge(name: str) -> float:
        try:
            return float(REGISTRY.get_sample_value(name) or 0)
        except Exception:
            return 0.0
    return {
        "users": users, "organizations": orgs, "meetings": meetings,
        "live_meetings": live_meetings, "documents": docs,
        "failed_documents": failed_docs,
        "active_ws_sessions": gauge("gt_ws_connections_active"),
        "active_participants": gauge("gt_active_participants"),
        "queue_depth": depths, "ai_health": ai_health,
        "cache_backend": type(cache()).__name__,
    }


@admin_router.get("/users", response_model=list[dict])
async def admin_users(principal: Principal = Depends(_require_platform_admin),
                      db: AsyncSession = Depends(get_db),
                      limit: int = Query(default=100, le=500),
                      q: str = Query(default="")):
    query = select(M.User)
    if q:
        query = query.where(M.User.email.ilike(f"%{q}%"))
    res = await db.execute(query.order_by(M.User.created_at.desc()).limit(limit))
    return [{"id": str(u.id), "email": u.email, "name": u.name,
             "status": u.status, "admin": u.is_platform_admin,
             "created_at": u.created_at.isoformat()} for u in res.scalars().all()]


@admin_router.post("/users/{user_id}/suspend", status_code=200)
async def admin_suspend(user_id: uuid.UUID, suspend: bool = Query(default=True),
                        principal: Principal = Depends(_require_platform_admin),
                        db: AsyncSession = Depends(get_db)):
    user = await db.get(M.User, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    user.status = "suspended" if suspend else "active"
    await audit_service.record(db, action="admin.user_status_changed",
                               actor_id=principal.user_id, resource_type="user",
                               resource_id=str(user_id),
                               details={"status": user.status})
    await db.commit()
    return {"id": str(user_id), "status": user.status}


@admin_router.get("/organizations", response_model=list[dict])
async def admin_orgs(principal: Principal = Depends(_require_platform_admin),
                     db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(M.Organization)
                           .order_by(M.Organization.created_at.desc()).limit(200))
    return [{"id": str(o.id), "name": o.name, "slug": o.slug, "plan": o.plan,
             "status": o.status, "created_at": o.created_at.isoformat()}
            for o in res.scalars().all()]


@admin_router.get("/audit-logs", response_model=list[AuditLogOut])
async def admin_audit(principal: Principal = Depends(_require_platform_admin),
                      db: AsyncSession = Depends(get_db),
                      org_id: str = Query(default=""),
                      action: str = Query(default=""),
                      limit: int = Query(default=100, le=500)):
    res = await audit_service.list_events(
        db, uuid.UUID(org_id) if org_id else None,
        action=action or None, limit=limit)
    return [AuditLogOut.model_validate(e) for e in res]


@admin_router.get("/languages", response_model=list[dict])
async def admin_languages(principal: Principal = Depends(_require_platform_admin),
                          db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(M.LanguageCapability))
    return [{"code": r.code, "name": r.name,
             "translation": r.translation_status, "speech_in": r.speech_input_status,
             "speech_out": r.speech_output_status, "realtime": r.realtime_status,
             "document": r.document_status} for r in res.scalars().all()]


class LangStatusUpdate(BaseModel):
    code: str
    capability: str = Field(pattern="^(translation_status|speech_input_status|speech_output_status|realtime_status|document_status)$")
    status: str = Field(pattern="^(EXPERIMENTAL|BETA|SUPPORTED|PRODUCTION)$")
    reason: str = ""


@admin_router.put("/languages/status", response_model=dict)
async def admin_update_language(body: LangStatusUpdate,
                                principal: Principal = Depends(_require_platform_admin),
                                db: AsyncSession = Depends(get_db)):
    """Capability promotion/demotion — gated on evaluation evidence (PDD §8)."""
    lang = await db.get(M.LanguageCapability, body.code)
    if lang is None:
        raise NotFoundError("Language not found.")
    old = getattr(lang, body.capability)
    setattr(lang, body.capability, body.status)
    await audit_service.record(db, action="admin.language_status_changed",
                               actor_id=principal.user_id,
                               resource_type="language", resource_id=body.code,
                               details={"capability": body.capability, "from": old,
                                        "to": body.status, "reason": body.reason})
    await db.commit()
    return {"code": body.code, "capability": body.capability,
            "from": old, "to": body.status}


@admin_router.get("/model-health", response_model=dict)
async def admin_model_health(principal: Principal = Depends(_require_platform_admin)):
    from app.ai import ai
    assert ai.router is not None
    out = {}
    for (task, name), h in ai.router.health.items():
        out[f"{task}/{name}"] = {
            "available": h.available, "ewma_latency_ms": round(h.ewma_latency_ms, 1),
            "error_rate": round(h.error_rate, 3), "requests": h.request_count}
    return out


@admin_router.get("/quality-evaluations", response_model=list[dict])
async def admin_evals(principal: Principal = Depends(_require_platform_admin),
                      db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(M.QualityEvaluation)
                           .order_by(M.QualityEvaluation.created_at.desc()).limit(100))
    return [{"id": str(e.id), "pair": e.pair, "domain": e.domain,
             "dataset": e.dataset, "bleu_avg": e.bleu_avg, "failure_rate": e.failure_rate,
             "passed_gates": e.passed_gates, "method": e.method,
             "created_at": e.created_at.isoformat()} for e in res.scalars().all()]


class FlagUpdate(BaseModel):
    key: str
    enabled: bool
    org_id: str = ""


@admin_router.put("/flags", response_model=dict)
async def admin_set_flag(body: FlagUpdate,
                         principal: Principal = Depends(_require_platform_admin),
                         db: AsyncSession = Depends(get_db)):
    flag = await db.get(M.FeatureFlag, body.key)
    if flag is None:
        flag = M.FeatureFlag(key=body.key, enabled_default=body.enabled)
        db.add(flag)
    else:
        if body.org_id:
            overrides = dict(flag.org_overrides_json or {})
            overrides[body.org_id] = body.enabled
            flag.org_overrides_json = overrides
        else:
            flag.enabled_default = body.enabled
    await audit_service.record(db, action="admin.flag_changed",
                               actor_id=principal.user_id, resource_type="flag",
                               resource_id=body.key,
                               details={"enabled": body.enabled, "org": body.org_id})
    await db.commit()
    return {"key": body.key, "enabled": body.enabled, "org_id": body.org_id or None}
