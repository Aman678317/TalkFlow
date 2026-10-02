"""Request context middleware: request_id/trace_id, structured access log, security headers, metrics."""
from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from globaltalk.core.logging import (get_logger, request_id_var, tenant_id_var, trace_id_var,
                                     user_id_var)
from globaltalk.core.metrics import metrics

log = get_logger("http")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        trace_id = request.headers.get("x-trace-id") or request_id
        request.state.request_id = request_id
        request.state.trace_id = trace_id
        request_id_var.set(request_id)
        trace_id_var.set(trace_id)
        tenant_id_var.set("-")
        user_id_var.set("-")
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            metrics.observe_request(request.url.path, 500, time.perf_counter() - started)
            raise
        elapsed = time.perf_counter() - started
        metrics.observe_request(request.url.path, response.status_code, elapsed)
        response.headers["x-request-id"] = request_id
        response.headers["x-trace-id"] = trace_id
        # Security headers (TLS termination may add HSTS upstream)
        response.headers.setdefault("x-content-type-options", "nosniff")
        response.headers.setdefault("x-frame-options", "DENY")
        response.headers.setdefault("referrer-policy", "no-referrer")
        response.headers.setdefault("permissions-policy",
                                    "camera=(self), microphone=(self), display-capture=(self)")
        if not request.url.path.startswith("/ws"):
            log.info("http_request", extra={
                "method": request.method, "path": request.url.path,
                "status": response.status_code, "duration_ms": round(elapsed * 1000, 2)})
        return response
