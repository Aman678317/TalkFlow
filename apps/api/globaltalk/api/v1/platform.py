"""Platform routes: API keys, usage, billing, webhooks, team/org management, admin,
feedback, search, agent bridge, voice session tokens."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from globaltalk.core.audit import audit, meter, usage_summary
from globaltalk.core.config import settings
from globaltalk.core.db import get_db
from globaltalk.core.deps import (Principal, ensure_org_member, get_principal,
                                  require_permission, require_platform_admin)
from globaltalk.core.errors import NotFoundError, ValidationError
from globaltalk.core.flags import DEFAULT_FLAGS, flag_enabled
from globaltalk.core.security import generate_api_key, generate_webhook_signing_secret
from globaltalk.models import (ApiKey, AuditLog, BillingEvent, ChatMessage, Document,
                               Feedback, FeatureFlag, Meeting, Organization,
                               OrganizationMember, Subscription, TranscriptSegment,
                               TranslationMemory, User, Webhook, WebhookDelivery)
from globaltalk.schemas import (ApiKeyCreate, ApiKeyCreated, ApiKeyOut, BridgeTurnIn,
                                FeedbackIn, MemberIn, MemberOut, UsageOut, WebhookIn,
                                WebhookOut)

router = APIRouter(tags=["platform"])

# ------------------------------------------------------------------ API keys

KEY_SCOPES = {"translate", "detect", "documents", "glossaries", "meetings", "usage", "admin"}


@router.get("/api-keys", response_model=list[ApiKeyOut])
def list_api_keys(principal: Principal = Depends(require_permission("manage_api_keys")),
                  db: Session = Depends(get_db)):
    rows = (db.query(ApiKey).filter(ApiKey.org_id == principal.org_id)
            .order_by(ApiKey.created_at.desc()).all())
    return [ApiKeyOut(id=k.id, name=k.name, prefix=k.prefix, scopes=k.scopes or [],
                      created_at=k.created_at, last_used_at=k.last_used_at, revoked=k.revoked)
            for k in rows]


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
def create_api_key(body: ApiKeyCreate,
                   principal: Principal = Depends(require_permission("manage_api_keys")),
                   db: Session = Depends(get_db)):
    unknown = set(body.scopes) - KEY_SCOPES
    if unknown:
        raise ValidationError(f"Unknown scopes: {sorted(unknown)}", code="bad_scopes")
    full, prefix, key_hash = generate_api_key()
    row = ApiKey(org_id=principal.org_id, user_id=principal.user_id or "", name=body.name,
                 prefix=prefix, key_hash=key_hash, scopes=body.scopes)
    db.add(row)
    db.commit()
    audit(db, "api_key.create", org_id=principal.org_id, actor_user_id=principal.user_id,
          resource_type="api_key", resource_id=row.id, details={"prefix": prefix})
    return ApiKeyCreated(id=row.id, name=row.name, prefix=prefix, scopes=row.scopes or [],
                         created_at=row.created_at, last_used_at=None, revoked=False,
                         key=full)


@router.post("/api-keys/{key_id}/rotate", response_model=ApiKeyCreated)
def rotate_api_key(key_id: str,
                   principal: Principal = Depends(require_permission("manage_api_keys")),
                   db: Session = Depends(get_db)):
    row = (db.query(ApiKey).filter(ApiKey.id == key_id,
                                   ApiKey.org_id == principal.org_id).first())
    if not row:
        raise NotFoundError("API key not found")
    full, prefix, key_hash = generate_api_key()
    row.revoked = True
    new = ApiKey(org_id=row.org_id, user_id=row.user_id, name=f"{row.name} (rotated)",
                 prefix=prefix, key_hash=key_hash, scopes=row.scopes)
    db.add(new)
    db.commit()
    audit(db, "api_key.rotate", org_id=row.org_id, actor_user_id=principal.user_id,
          resource_type="api_key", resource_id=row.id)
    _emit_webhook(db, row.org_id, "api_key.revoked", {"api_key_id": row.id,
                                                      "prefix": row.prefix})
    return ApiKeyCreated(id=new.id, name=new.name, prefix=prefix, scopes=new.scopes or [],
                         created_at=new.created_at, last_used_at=None, revoked=False,
                         key=full)


@router.post("/api-keys/{key_id}/revoke", status_code=204)
def revoke_api_key(key_id: str,
                   principal: Principal = Depends(require_permission("manage_api_keys")),
                   db: Session = Depends(get_db)):
    row = (db.query(ApiKey).filter(ApiKey.id == key_id,
                                   ApiKey.org_id == principal.org_id).first())
    if not row:
        raise NotFoundError("API key not found")
    row.revoked = True
    db.commit()
    audit(db, "api_key.revoke", org_id=row.org_id, actor_user_id=principal.user_id,
          resource_type="api_key", resource_id=row.id)
    _emit_webhook(db, row.org_id, "api_key.revoked", {"api_key_id": row.id})


def _emit_webhook(db: Session, org_id: str, event: str, payload: dict) -> None:
    try:
        from globaltalk.services.webhooks import dispatch_event
        dispatch_event(db, org_id, event, payload)
    except Exception:
        pass


# ------------------------------------------------------------------ usage & billing

@router.get("/usage", response_model=UsageOut)
def get_usage(principal: Principal = Depends(require_permission("view_usage")),
              db: Session = Depends(get_db), days: int = Query(default=30, le=365)):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    totals = usage_summary(db, principal.org_id, since)
    sub = (db.query(Subscription).filter(Subscription.org_id == principal.org_id).first())
    from globaltalk.services.billing import PLAN_LIMITS
    return UsageOut(totals=totals, plan=sub.plan if sub else "free",
                    limits=PLAN_LIMITS.get(sub.plan if sub else "free", {}),
                    period_start=sub.current_period_start if sub else None)


@router.get("/billing/invoices")
def list_invoices(principal: Principal = Depends(require_permission("manage_billing")),
                  db: Session = Depends(get_db)):
    rows = (db.query(BillingEvent)
            .filter(BillingEvent.org_id == principal.org_id,
                    BillingEvent.event_type == "invoice")
            .order_by(BillingEvent.created_at.desc()).limit(24).all())
    return [{"id": r.id, "amount_cents": r.amount_cents, "currency": r.currency,
             "period_start": r.period_start, "period_end": r.period_end,
             "breakdown": r.breakdown, "status": r.status, "created_at": r.created_at}
            for r in rows]


@router.post("/billing/checkout-preview")
def billing_preview(principal: Principal = Depends(require_permission("view_usage")),
                    db: Session = Depends(get_db)):
    from globaltalk.services.billing import compute_invoice
    return compute_invoice(db, principal.org_id, preview=True)


# ------------------------------------------------------------------ webhooks

WEBHOOK_EVENTS = ["translation.completed", "document.completed", "meeting.started",
                  "meeting.ended", "transcript.completed", "translation.failed",
                  "document.failed", "usage.threshold", "api_key.revoked"]


@router.get("/webhooks", response_model=list[WebhookOut])
def list_webhooks(principal: Principal = Depends(require_permission("manage_webhooks")),
                  db: Session = Depends(get_db)):
    rows = db.query(Webhook).filter(Webhook.org_id == principal.org_id).all()
    return [WebhookOut(id=w.id, url=w.url, events=w.events or [], enabled=w.enabled,
                       description=w.description, created_at=w.created_at) for w in rows]


@router.post("/webhooks", response_model=dict, status_code=201)
def create_webhook(body: WebhookIn,
                   principal: Principal = Depends(require_permission("manage_webhooks")),
                   db: Session = Depends(get_db)):
    unknown = set(body.events) - set(WEBHOOK_EVENTS) - {"*"}
    if unknown:
        raise ValidationError(f"Unknown events: {sorted(unknown)}", code="bad_events")
    secret = generate_webhook_signing_secret()
    w = Webhook(org_id=principal.org_id, url=body.url, events=body.events or ["*"],
                signing_secret=secret, description=body.description)
    db.add(w)
    db.commit()
    audit(db, "webhook.create", org_id=principal.org_id, actor_user_id=principal.user_id,
          resource_type="webhook", resource_id=w.id)
    return {"id": w.id, "url": w.url, "events": w.events,
            "signing_secret": secret}  # shown once; signature = HMAC SHA-256 (section 49)


@router.delete("/webhooks/{hook_id}", status_code=204)
def delete_webhook(hook_id: str,
                   principal: Principal = Depends(require_permission("manage_webhooks")),
                   db: Session = Depends(get_db)):
    w = db.query(Webhook).filter(Webhook.id == hook_id,
                                 Webhook.org_id == principal.org_id).first()
    if not w:
        raise NotFoundError("Webhook not found")
    db.delete(w)
    db.commit()


@router.get("/webhooks/deliveries")
def list_deliveries(principal: Principal = Depends(require_permission("manage_webhooks")),
                    db: Session = Depends(get_db), limit: int = 50):
    hook_ids = [w.id for w in db.query(Webhook).filter(
        Webhook.org_id == principal.org_id).all()]
    rows = (db.query(WebhookDelivery)
            .filter(WebhookDelivery.webhook_id.in_(hook_ids or ["-"]))
            .order_by(WebhookDelivery.created_at.desc()).limit(limit).all())
    return [{"id": r.id, "event_type": r.event_type, "status": r.status,
             "attempts": r.attempts, "last_error": r.last_error,
             "created_at": r.created_at} for r in rows]


# ------------------------------------------------------------------ team / org

@router.get("/org", response_model=dict)
def get_org(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    org = db.get(Organization, principal.org_id)
    return {"id": org.id, "name": org.name, "slug": org.slug, "plan": org.plan,
            "settings": org.settings or {}, "retention_policy": org.retention_policy or {}}


@router.get("/members", response_model=list[MemberOut])
def list_members(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    rows = (db.query(OrganizationMember, User)
            .join(User, User.id == OrganizationMember.user_id)
            .filter(OrganizationMember.org_id == principal.org_id).all())
    return [MemberOut(user_id=u.id, email=u.email, full_name=u.full_name, role=m.role,
                      joined_at=m.created_at) for m, u in rows]


@router.post("/members", response_model=MemberOut, status_code=201)
def add_member(body: MemberIn,
               principal: Principal = Depends(require_permission("manage_members")),
               db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user:
        raise NotFoundError("No user with this email. They must sign up first "
                            "(invite emails are queued in production deployments).",
                            code="user_not_found")
    existing = (db.query(OrganizationMember)
                .filter(OrganizationMember.org_id == principal.org_id,
                        OrganizationMember.user_id == user.id).first())
    if existing:
        existing.role = body.role
        db.commit()
        audit(db, "member.update_role", org_id=principal.org_id,
              actor_user_id=principal.user_id, resource_type="user", resource_id=user.id,
              details={"role": body.role})
        return MemberOut(user_id=user.id, email=user.email, full_name=user.full_name,
                         role=body.role, joined_at=existing.created_at)
    m = OrganizationMember(org_id=principal.org_id, user_id=user.id, role=body.role)
    db.add(m)
    db.commit()
    audit(db, "member.add", org_id=principal.org_id, actor_user_id=principal.user_id,
          resource_type="user", resource_id=user.id, details={"role": body.role})
    return MemberOut(user_id=user.id, email=user.email, full_name=user.full_name,
                     role=body.role, joined_at=m.created_at)


@router.delete("/members/{user_id}", status_code=204)
def remove_member(user_id: str,
                  principal: Principal = Depends(require_permission("manage_members")),
                  db: Session = Depends(get_db)):
    m = (db.query(OrganizationMember)
         .filter(OrganizationMember.org_id == principal.org_id,
                 OrganizationMember.user_id == user_id).first())
    if not m:
        raise NotFoundError("Member not found")
    if m.role == "owner":
        owners = (db.query(OrganizationMember)
                  .filter(OrganizationMember.org_id == principal.org_id,
                          OrganizationMember.role == "owner").count())
        if owners <= 1:
            raise ValidationError("Cannot remove the last owner", code="last_owner")
    db.delete(m)
    db.commit()
    audit(db, "member.remove", org_id=principal.org_id, actor_user_id=principal.user_id,
          resource_type="user", resource_id=user_id)


# ------------------------------------------------------------------ search (section 47)

@router.get("/search")
def search(q: str = Query(min_length=2, max_length=200),
           principal: Principal = Depends(get_principal), db: Session = Depends(get_db),
           limit: int = Query(default=10, le=50)):
    """PostgreSQL full-text-ready search (ILIKE now; tsvector/SearchAdapter later —
    globaltalk.core.search isolates the backend)."""
    from globaltalk.core.search import search_all
    return search_all(db, principal.org_id, q, limit)


# ------------------------------------------------------------------ feedback

@router.post("/feedback", status_code=201)
def submit_feedback(body: FeedbackIn, principal: Principal = Depends(get_principal),
                    db: Session = Depends(get_db)):
    row = Feedback(org_id=principal.org_id, user_id=principal.user_id, kind=body.kind,
                   target_id=body.target_id, rating=body.rating, comment=body.comment,
                   context=body.context)
    db.add(row)
    db.commit()
    return {"id": row.id}


# ------------------------------------------------------------------ voice session (LiveKit token / WS info)

@router.post("/voice/session")
def voice_session(meeting_id: str,
                  principal: Principal = Depends(require_permission("create_meeting")),
                  db: Session = Depends(get_db)):
    m = db.query(Meeting).filter(Meeting.id == meeting_id,
                                 Meeting.org_id == principal.org_id).first()
    if not m:
        raise NotFoundError("Meeting not found")
    if not flag_enabled(db, "voice_translation", principal.org_id):
        raise ValidationError("Voice translation is disabled for this organization",
                              code="feature_disabled")
    if settings.livekit_configured:
        from services.realtime.livekit_adapter import adapter
        identity = f"user-{principal.user_id or 'guest'}"
        token = adapter.create_participant_token(
            m.room_name, identity,
            principal.user.full_name if principal.user else "Guest",
            metadata={"meeting_id": m.id})
        return {"transport": "livekit", "url": settings.livekit_url, "room": m.room_name,
                "token": token, "ws_url": None}
    ws_scheme = "wss" if settings.api_base_url.startswith("https") else "ws"
    host = settings.api_base_url.split("://", 1)[-1]
    return {"transport": "websocket", "url": None, "room": m.room_name, "token": None,
            "ws_url": f"{ws_scheme}://{host}/ws/meetings/{m.id}"}


# ------------------------------------------------------------------ agent bridge (section 22)

bridge_router = APIRouter(prefix="/bridge", tags=["agent-bridge"])


@bridge_router.post("/turn")
def bridge_turn(body: BridgeTurnIn, agents: str = Query(default="agent-a:en,agent-b:ja"),
                principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    """Human source → canonical representation → INDEPENDENT per-agent-language outputs.

    Agents never receive another agent's translation as input; every output is derived
    from the canonical human text. Deterministic infrastructure (this service) owns routing
    and sequencing — agents only transform text within their language."""
    if not flag_enabled(db, "agent_bridge", principal.org_id):
        raise ValidationError("Agent bridge is disabled (feature flag agent_bridge)",
                              code="feature_disabled")
    from globaltalk.services.bridge import run_bridge_turn
    agent_specs = []
    for part in agents.split(","):
        name, _, lang = part.strip().partition(":")
        if name and lang:
            agent_specs.append({"name": name, "language": lang})
    if not agent_specs:
        raise ValidationError("At least one agent (name:lang) required", code="bad_agents")
    result = run_bridge_turn(db, org_id=principal.org_id, text=body.text,
                             source_language=body.source_language, agents=agent_specs,
                             user_id=principal.user_id)
    return result


# ------------------------------------------------------------------ admin

admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.get("/overview")
def admin_overview(principal: Principal = Depends(require_platform_admin),
                   db: Session = Depends(get_db)):
    from globaltalk.realtime.hub import hub
    return {
        "users": db.query(User).count(),
        "organizations": db.query(Organization).count(),
        "meetings": db.query(Meeting).count(),
        "meetings_live": db.query(Meeting).filter(Meeting.status == "live").count(),
        "documents": db.query(Document).count(),
        "documents_failed": db.query(Document).filter(Document.status == "failed").count(),
        "transcript_segments": db.query(TranscriptSegment).count(),
        "tm_entries": db.query(TranslationMemory).count(),
        "active_ws_sessions": hub.active_meetings(),
        "active_ws_participants": hub.active_participants(),
    }


@admin_router.get("/users")
def admin_users(principal: Principal = Depends(require_platform_admin),
                db: Session = Depends(get_db), limit: int = 100):
    rows = db.query(User).order_by(User.created_at.desc()).limit(limit).all()
    return [{"id": u.id, "email": u.email, "full_name": u.full_name,
             "is_active": u.is_active, "is_platform_admin": u.is_platform_admin,
             "email_verified": u.email_verified, "created_at": u.created_at,
             "last_login_at": u.last_login_at} for u in rows]


@admin_router.post("/users/{user_id}/deactivate")
def admin_deactivate(user_id: str,
                     principal: Principal = Depends(require_platform_admin),
                     db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise NotFoundError("User not found")
    u.is_active = False
    db.commit()
    audit(db, "admin.user_deactivate", actor_user_id=principal.user_id,
          resource_type="user", resource_id=user_id)
    return {"id": u.id, "is_active": u.is_active}


@admin_router.get("/audit-logs")
def admin_audit(principal: Principal = Depends(require_platform_admin),
                db: Session = Depends(get_db), org_id: str | None = None,
                limit: int = Query(default=100, le=500)):
    q = db.query(AuditLog)
    if org_id:
        q = q.filter(AuditLog.org_id == org_id)
    rows = q.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return [{"id": r.id, "org_id": r.org_id, "action": r.action, "actor_user_id": r.actor_user_id,
             "resource_type": r.resource_type, "resource_id": r.resource_id,
             "ip_address": r.ip_address, "details": r.details,
             "created_at": r.created_at.isoformat()} for r in rows]


@admin_router.get("/feature-flags")
def admin_flags(principal: Principal = Depends(require_platform_admin),
                db: Session = Depends(get_db)):
    rows = db.query(FeatureFlag).all()
    out = {name: meta for name, meta in DEFAULT_FLAGS.items()}
    for r in rows:
        out.setdefault(r.name, {})["enabled"] = r.enabled
        out[r.name]["org_id"] = r.org_id
        out[r.name]["db"] = True
    return out


@admin_router.put("/feature-flags/{name}")
def admin_set_flag(name: str, enabled: bool, org_id: str | None = None,
                   principal: Principal = Depends(require_platform_admin),
                   db: Session = Depends(get_db)):
    row = (db.query(FeatureFlag)
           .filter(FeatureFlag.name == name,
                   FeatureFlag.org_id.is_(None) if org_id is None
                   else FeatureFlag.org_id == org_id).first())
    if not row:
        row = FeatureFlag(name=name, org_id=org_id, enabled=enabled)
        db.add(row)
    else:
        row.enabled = enabled
    db.commit()
    audit(db, "admin.feature_flag", actor_user_id=principal.user_id,
          resource_type="feature_flag", resource_id=name, details={"enabled": enabled})
    return {"name": name, "enabled": enabled, "org_id": org_id}


@admin_router.get("/security-events")
def admin_security_events(principal: Principal = Depends(require_platform_admin),
                          db: Session = Depends(get_db), limit: int = 100):
    rows = (db.query(AuditLog)
            .filter(or_(AuditLog.action.ilike("%failed%"),
                        AuditLog.action.ilike("%revoke%"),
                        AuditLog.action.ilike("%deactivate%"),
                        AuditLog.action.ilike("%security%")))
            .order_by(AuditLog.created_at.desc()).limit(limit).all())
    return [{"action": r.action, "org_id": r.org_id, "ip_address": r.ip_address,
             "details": r.details, "created_at": r.created_at.isoformat()} for r in rows]
