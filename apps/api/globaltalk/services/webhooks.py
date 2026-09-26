"""Webhook dispatch with HMAC signatures, retries and delivery log (section 49)."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from globaltalk.core.logging import get_logger
from globaltalk.core.queue import QUEUE_WEBHOOKS, push
from globaltalk.core.security import webhook_signature
from globaltalk.models import Webhook, WebhookDelivery

log = get_logger("webhooks")

RETRY_DELAYS_S = [5, 30, 120, 600, 1800]  # exponential-ish backoff, max 5 attempts


def dispatch_event(db: Session, org_id: str, event_type: str, payload: dict) -> None:
    hooks = (db.query(Webhook).filter(Webhook.org_id == org_id,
                                      Webhook.enabled.is_(True)).all())
    for hook in hooks:
        events = hook.events or []
        if events and event_type not in events and "*" not in events:
            continue
        body = {"event": event_type, "created_at": datetime.now(timezone.utc).isoformat(),
                "data": payload}
        delivery = WebhookDelivery(webhook_id=hook.id, event_type=event_type, payload=body,
                                   status="pending",
                                   next_attempt_at=datetime.now(timezone.utc))
        db.add(delivery)
        db.commit()
        push(QUEUE_WEBHOOKS, {"delivery_id": delivery.id})


def deliver(db: Session, delivery_id: str) -> None:
    delivery = db.get(WebhookDelivery, delivery_id)
    if not delivery or delivery.status == "delivered":
        return
    hook = db.get(Webhook, delivery.webhook_id)
    if not hook or not hook.enabled:
        delivery.status = "failed"
        delivery.last_error = "webhook disabled/deleted"
        db.commit()
        return
    delivery.attempts += 1
    body = json.dumps(delivery.payload, separators=(",", ":"), default=str).encode()
    ts = int(time.time())
    sig = webhook_signature(body, hook.signing_secret, ts)
    headers = {
        "content-type": "application/json",
        "globaltalk-event": delivery.event_type,
        "globaltalk-delivery": delivery.id,
        "globaltalk-timestamp": str(ts),
        "globaltalk-signature": sig,
        "user-agent": "globaltalk-webhooks/1",
    }
    try:
        # SSRF guard: block private/internal targets unless explicitly allowed in dev
        _guard_ssrf(hook.url)
        r = httpx.post(hook.url, content=body, headers=headers, timeout=10,
                       follow_redirects=False)
        if 200 <= r.status_code < 300:
            delivery.status = "delivered"
            delivery.delivered_at = datetime.now(timezone.utc)
            delivery.last_error = ""
        else:
            raise RuntimeError(f"HTTP {r.status_code}")
    except Exception as exc:
        delivery.last_error = str(exc)[:500]
        if delivery.attempts < len(RETRY_DELAYS_S) + 1:
            delay = RETRY_DELAYS_S[min(delivery.attempts - 1, len(RETRY_DELAYS_S) - 1)]
            delivery.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            delivery.status = "pending"
            push(QUEUE_WEBHOOKS, {"delivery_id": delivery.id, "delay_s": delay})
        else:
            delivery.status = "failed"
        log.warning("webhook_delivery_failed", extra={"id": delivery.id,
                                                      "error": delivery.last_error})
    db.commit()


def _guard_ssrf(url: str) -> None:
    import ipaddress
    import socket
    from urllib.parse import urlparse
    u = urlparse(url)
    if u.scheme not in ("http", "https"):
        raise RuntimeError("invalid scheme")
    host = u.hostname or ""
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0", "metadata.google.internal"):
        from globaltalk.core.config import settings
        if settings.app_env == "production":
            raise RuntimeError("loopback webhook targets are forbidden in production")
        return
    try:
        infos = socket.getaddrinfo(host, None)
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast):
                from globaltalk.core.config import settings
                if settings.app_env == "production":
                    raise RuntimeError("private-network webhook targets are forbidden")
    except socket.gaierror:
        raise RuntimeError("webhook host does not resolve")
