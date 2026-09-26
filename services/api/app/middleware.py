"""HTTP middleware: request IDs, structured access logs, timing metrics,
security headers (PDD §39, §42)."""
from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app import context
from app import metrics as met

log = logging.getLogger("app.access")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(self), microphone=(self), display-capture=(self)",
    "Cross-Origin-Opener-Policy": "same-origin",
}


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        trace_id = request.headers.get("X-Trace-ID") or uuid.uuid4().hex
        context.new_ctx(request_id=request_id, trace_id=trace_id)

        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - t0

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Trace-ID"] = trace_id
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if request.url.path.startswith("/api") or request.url.path in ("/health", "/ready"):
            met.HTTP_REQUESTS.labels(method=request.method,
                                     path=_norm_path(request),
                                     status=response.status_code).inc()
            met.HTTP_LATENCY.labels(method=request.method,
                                    path=_norm_path(request)).observe(elapsed)
        log.info("%s %s -> %d in %.1fms", request.method, request.url.path,
                 response.status_code, elapsed * 1000)
        return response


def _norm_path(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path or request.url.path
