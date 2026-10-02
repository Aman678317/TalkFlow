"""Structured errors. Every API error carries code/message/request_id/trace_id/recoverable/details."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    http_status = 400
    code = "app_error"
    recoverable = False

    def __init__(self, message: str, *, details: dict[str, Any] | None = None,
                 http_status: int | None = None, code: str | None = None,
                 recoverable: bool | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if http_status is not None:
            self.http_status = http_status
        if code is not None:
            self.code = code
        if recoverable is not None:
            self.recoverable = recoverable

    def to_dict(self, request_id: str, trace_id: str) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "request_id": request_id,
                "trace_id": trace_id,
                "recoverable": self.recoverable,
                "details": self.details,
            }
        }


class NotFoundError(AppError):
    http_status = 404
    code = "not_found"


class UnauthorizedError(AppError):
    http_status = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    http_status = 403
    code = "forbidden"


class ValidationError(AppError):
    http_status = 422
    code = "validation_error"
    recoverable = True


class RateLimitedError(AppError):
    http_status = 429
    code = "rate_limited"
    recoverable = True


class ConflictError(AppError):
    http_status = 409
    code = "conflict"


class UpstreamAIError(AppError):
    http_status = 502
    code = "ai_provider_error"
    recoverable = True


class StorageError(AppError):
    http_status = 500
    code = "storage_error"
    recoverable = True


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        rid = getattr(request.state, "request_id", uuid.uuid4().hex[:12])
        tid = getattr(request.state, "trace_id", rid)
        return JSONResponse(exc.to_dict(rid, tid), status_code=exc.http_status)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        rid = getattr(request.state, "request_id", uuid.uuid4().hex[:12])
        err = AppError(str(exc.detail), http_status=exc.status_code,
                       code=f"http_{exc.status_code}", recoverable=exc.status_code < 500)
        return JSONResponse(err.to_dict(rid, rid), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        rid = getattr(request.state, "request_id", uuid.uuid4().hex[:12])
        err = ValidationError("Request validation failed",
                              details={"errors": [
                                  {"loc": list(map(str, e["loc"])), "msg": e["msg"]}
                                  for e in exc.errors()[:20]]})
        return JSONResponse(err.to_dict(rid, rid), status_code=422)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        rid = getattr(request.state, "request_id", uuid.uuid4().hex[:12])
        from globaltalk.core.logging import get_logger
        get_logger("errors").exception("unhandled_error", extra={"request_id": rid})
        err = AppError("Internal server error", http_status=500, code="internal_error",
                       recoverable=False, details={"exception": type(exc).__name__})
        return JSONResponse(err.to_dict(rid, rid), status_code=500)
