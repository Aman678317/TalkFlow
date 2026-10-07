"""HTTP middleware: request IDs, structured access logs, timing metrics,
security headers, CSRF protection (PDD §39, §42)."""
from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app import context
from app import metrics as met

import re

log = logging.getLogger("app.access")

_UUID_OR_HEX_RE = re.compile(r"/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?=/|$)")
_HEX_ID_RE = re.compile(r"/[0-9a-fA-F]{24,36}(?=/|$)")
_NUM_ID_RE = re.compile(r"/\d+(?=/|$)")

# Endpoints exempt from CSRF validation because they are the entry-points
# that *issue* the CSRF cookie (or are idempotent reads).
_CSRF_EXEMPT_PATHS = frozenset({
    "/api/v1/auth/login",
    "/api/v1/auth/signup",
    "/api/v1/auth/social-login",
    "/api/v1/auth/refresh",
    "/api/v1/auth/password-reset/request",
    "/api/v1/auth/password-reset/confirm",
    "/api/v1/auth/verify-email",
    "/health",
    "/ready",
    "/metrics",
})
_CSRF_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit cookie CSRF protection.

    Cookie-authenticated state-changing requests must include
    ``X-TalkFlow-CSRF`` header whose value matches the ``csrf_token`` cookie.
    The cookie is set by login/signup/refresh responses and is readable by JS
    (not HttpOnly) but SameSite=Lax.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        has_auth_header = bool(request.headers.get("authorization"))
        if (
            request.method not in _CSRF_SAFE_METHODS
            and request.url.path not in _CSRF_EXEMPT_PATHS
            and not has_auth_header
            and request.cookies.get("refresh_token")  # cookie auth is active
        ):
            cookie_csrf = request.cookies.get("csrf_token", "")
            header_csrf = request.headers.get("x-talkflow-csrf", "")
            if not cookie_csrf or not header_csrf or cookie_csrf != header_csrf:
                met.SECURITY_VIOLATIONS.labels(type="csrf_failed").inc()
                return JSONResponse(
                    {"detail": "CSRF validation failed."},
                    status_code=403,
                )
        return await call_next(request)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(self), microphone=(self), display-capture=(self)",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self';",
}


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]

        trace_id = None
        traceparent = request.headers.get("traceparent")
        if traceparent:
            parts = traceparent.strip().split("-")
            if len(parts) >= 2 and len(parts[1]) == 32:
                trace_id = parts[1]
        if not trace_id:
            trace_id = request.headers.get("X-Trace-ID") or uuid.uuid4().hex

        context.new_ctx(request_id=request_id, trace_id=trace_id)

        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - t0

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Trace-ID"] = trace_id
        for k, v in SECURITY_HEADERS.items():
            if k == "Content-Security-Policy" and request.url.path in ("/api/docs", "/api/redoc", "/api/openapi.json"):
                response.headers.setdefault(k, "default-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; frame-ancestors 'none'; object-src 'none';")
            else:
                response.headers.setdefault(k, v)
        if request.url.path.startswith("/api") or request.url.path in ("/health", "/ready"):
            norm = _norm_path(request)
            met.HTTP_REQUESTS.labels(method=request.method,
                                     path=norm,
                                     status=response.status_code).inc()
            met.HTTP_LATENCY.labels(method=request.method,
                                     path=norm).observe(elapsed)
        log.info("%s %s -> %d in %.1fms", request.method, request.url.path,
                 response.status_code, elapsed * 1000)
        return response


def _norm_path(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if path:
        return path
    raw_path = request.url.path
    sanitized = _UUID_OR_HEX_RE.sub("/{id}", raw_path)
    sanitized = _HEX_ID_RE.sub("/{id}", sanitized)
    sanitized = _NUM_ID_RE.sub("/{id}", sanitized)
    return sanitized
