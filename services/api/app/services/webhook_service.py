"""Webhook delivery with HMAC signatures + retry policy (PDD §49)."""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import secrets
import socket
import uuid
from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import models as M
from app.db.base import utcnow
from app.queue import queue
from app.security import sign_webhook_payload

log = logging.getLogger("app.webhooks")

EVENT_TYPES = [
    "translation.completed", "document.completed", "meeting.started",
    "meeting.ended", "transcript.completed", "translation.failed",
    "document.failed", "usage.threshold", "api_key.revoked",
]

MAX_DELIVERY_ATTEMPTS = 5
RETRY_BACKOFF_S = [10, 60, 300, 900, 3600]


def generate_secret() -> str:
    return "whsec_" + secrets.token_hex(24)


async def register_endpoint(db: AsyncSession, org_id: uuid.UUID, url: str,
                            events: list[str],
                            created_by: uuid.UUID | None) -> M.WebhookEndpoint:
    from app.errors import ValidationError
    import urllib.parse
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValidationError("Webhook URL must use http or https scheme.")
    if not parsed.hostname:
        raise ValidationError("Invalid webhook URL host.")
    if settings.is_production:
        try:
            await _assert_public_url(url)
        except RuntimeError as exc:
            raise ValidationError(str(exc))

    for e in events:
        if e not in EVENT_TYPES:
            raise ValidationError(f"Unknown event type '{e}'.",
                                  details={"allowed": EVENT_TYPES})
    ep = M.WebhookEndpoint(org_id=org_id, url=url,
                           events=events or EVENT_TYPES,
                           secret=generate_secret(), created_by=created_by)
    db.add(ep)
    await db.commit()
    return ep


async def dispatch(db: AsyncSession, org_id: uuid.UUID, event: str,
                   payload: dict) -> int:
    """Fan an event out to matching endpoints via the job queue."""
    res = await db.execute(select(M.WebhookEndpoint).where(
        M.WebhookEndpoint.org_id == org_id,
        M.WebhookEndpoint.status == "active"))
    endpoints = [e for e in res.scalars().all() if event in (e.events or [])]
    for ep in endpoints:
        delivery = M.WebhookDelivery(
            endpoint_id=ep.id, event_type=event,
            payload_json={"event": event, "data": payload,
                          "org_id": str(org_id),
                          "created_at": utcnow().isoformat()},
            status="pending", attempts=0)
        db.add(delivery)
        await db.flush()
        await queue().push("webhook.deliver", {
            "endpoint_id": str(ep.id), "delivery_id": str(delivery.id)})
    await db.commit()
    return len(endpoints)


async def deliver_job(payload: dict) -> None:
    from app.db.session import db_session
    delivery_id = uuid.UUID(payload["delivery_id"])
    async with db_session() as db:
        delivery = await db.get(M.WebhookDelivery, delivery_id)
        if delivery is None or delivery.status == "delivered":
            return
        # If scheduled for a future backoff time, requeue and wait
        if delivery.next_retry_at and delivery.next_retry_at > utcnow():
            wait_s = (delivery.next_retry_at - utcnow()).total_seconds()
            if wait_s > 0.5:
                q = queue()
                if hasattr(q, "requeue"):
                    from app.queue import Job
                    re_job = Job(job_id=uuid.uuid4().hex, type="webhook.deliver", payload=payload)
                    await q.requeue(re_job, queue="webhooks", delay_s=wait_s)
                return
        ep = await db.get(M.WebhookEndpoint, delivery.endpoint_id)
        if ep is None or ep.status != "active":
            delivery.status = "failed"
            await db.commit()
            return
        body = json.dumps(delivery.payload_json, separators=(",", ":"),
                          default=str).encode()
        import time as _t
        ts = int(_t.time())
        sig = sign_webhook_payload(ep.secret, ts, body)
        headers = {
            "Content-Type": "application/json",
            "X-GlobalTalk-Signature": sig,
            "GlobalTalk-Signature": f"t={ts},{sig}",
            "X-GlobalTalk-Timestamp": str(ts),
            "X-GlobalTalk-Event": delivery.event_type,
            "X-GlobalTalk-Delivery": str(delivery.id),
            "User-Agent": "GlobalTalkAI-Webhooks/1",
        }
        delivery.attempts += 1
        try:
            await _assert_public_url(ep.url)
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as c:
                r = await c.post(ep.url, content=body, headers=headers)
            delivery.last_status_code = r.status_code
            if 200 <= r.status_code < 300:
                delivery.status = "delivered"
                delivery.delivered_at = utcnow()
            else:
                raise RuntimeError(f"endpoint returned {r.status_code}")
        except Exception as e:
            log.warning("webhook delivery %s attempt %d failed: %s",
                        delivery.id, delivery.attempts, e)
            if delivery.attempts < MAX_DELIVERY_ATTEMPTS:
                delay = RETRY_BACKOFF_S[min(delivery.attempts - 1,
                                            len(RETRY_BACKOFF_S) - 1)]
                delivery.status = "pending"
                delivery.next_retry_at = utcnow() + timedelta(seconds=delay)
                await db.commit()
                q = queue()
                if hasattr(q, "requeue"):
                    from app.queue import Job
                    re_job = Job(job_id=uuid.uuid4().hex, type="webhook.deliver",
                                 payload={"endpoint_id": str(ep.id), "delivery_id": str(delivery.id)})
                    await q.requeue(re_job, queue="webhooks", delay_s=float(delay))
                else:
                    async def _delayed_webhook_push():
                        await asyncio.sleep(delay)
                        await queue().push("webhook.deliver", {
                            "endpoint_id": str(ep.id), "delivery_id": str(delivery.id)},
                            queue="webhooks")
                    asyncio.create_task(_delayed_webhook_push())
                return
            delivery.status = "failed"
        await db.commit()


async def _assert_public_url(url: str, force_check: bool = False) -> None:
    """SSRF guard: resolve host and refuse private/link-local targets in prod."""
    from app import config as _cfg
    live_settings = getattr(_cfg, "settings", settings)
    is_prod = getattr(live_settings, "is_production", False) or getattr(live_settings, "app_env", "") == "production"
    if not is_prod and not force_check:
        return
    import urllib.parse
    parsed = urllib.parse.urlparse(url)
    if parsed.username or parsed.password:
        raise RuntimeError("webhook URL must not contain credentials")
    if parsed.scheme not in ("http", "https"):
        raise RuntimeError("webhook URL must use http or https scheme")
    host = parsed.hostname or ""
    if not host:
        raise RuntimeError("empty webhook host")

    blocked_hosts = {
        "localhost", "metadata.google.internal", "metadata", "instance-data",
        "169.254.169.254"
    }
    if host.lower() in blocked_hosts or host.lower().endswith(".internal") or host.lower().endswith(".local"):
        raise RuntimeError("webhook target resolves to a private address")

    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
    except socket.gaierror as e:
        raise RuntimeError(f"cannot resolve webhook host: {e}")
    if not infos:
        raise RuntimeError("cannot resolve webhook host")

    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            raise RuntimeError(f"invalid IP address resolved: {ip_str}")

        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped

        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise RuntimeError("webhook target resolves to a private address")
