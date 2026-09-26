"""Request context propagation (PDD §42 trace model).

trace_id -> request_id -> tenant_id -> user_id -> session_id -> meeting_id
Contextvars make every log line and error response carry the correlation IDs.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class RequestCtx:
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    tenant_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    meeting_id: str | None = None


_ctx: ContextVar[RequestCtx | None] = ContextVar("gt_request_ctx", default=None)


def current() -> RequestCtx:
    ctx = _ctx.get()
    if ctx is None:
        ctx = RequestCtx()
        _ctx.set(ctx)
    return ctx


def set_ctx(ctx: RequestCtx) -> None:
    _ctx.set(ctx)


def new_ctx(**kwargs) -> RequestCtx:
    ctx = RequestCtx(**kwargs)
    _ctx.set(ctx)
    return ctx


def bind(**kwargs) -> None:
    ctx = current()
    for k, v in kwargs.items():
        if hasattr(ctx, k):
            setattr(ctx, k, v)


def as_dict() -> dict:
    ctx = _ctx.get()
    if ctx is None:
        return {}
    return {
        "request_id": ctx.request_id,
        "trace_id": ctx.trace_id,
        "tenant_id": ctx.tenant_id,
        "user_id": ctx.user_id,
        "session_id": ctx.session_id,
        "meeting_id": ctx.meeting_id,
    }
