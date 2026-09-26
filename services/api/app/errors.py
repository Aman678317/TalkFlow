"""Structured error model (PDD §37).

Every API error responds with:
    {code, message, request_id, trace_id, recoverable, details}
Frontend maps codes to human-readable messages; realtime errors carry
explicit recovery hints.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import context


class AppError(Exception):
    """Base application error."""
    code: str = "internal_error"
    status: int = 500
    recoverable: bool = False

    def __init__(self, message: str = "", *, details: Any = None,
                 recoverable: bool | None = None, status: int | None = None) -> None:
        self.message = message or self.__class__.__doc__ or self.code
        self.details = details
        if recoverable is not None:
            self.recoverable = recoverable
        if status is not None:
            self.status = status
        super().__init__(self.message)


class ValidationError(AppError):
    """Request validation failed."""
    code = "validation_error"
    status = 422
    recoverable = True


class AuthenticationError(AppError):
    """Authentication required or failed."""
    code = "authentication_error"
    status = 401
    recoverable = True


class AuthorizationError(AppError):
    """You do not have permission to perform this action."""
    code = "authorization_error"
    status = 403
    recoverable = False


class NotFoundError(AppError):
    """Resource not found."""
    code = "not_found"
    status = 404
    recoverable = True


class ConflictError(AppError):
    """Resource state conflict."""
    code = "conflict"
    status = 409
    recoverable = True


class RateLimitError(AppError):
    """Rate limit exceeded. Retry later."""
    code = "rate_limited"
    status = 429
    recoverable = True


class QuotaExceededError(AppError):
    """Plan quota exceeded."""
    code = "quota_exceeded"
    status = 402
    recoverable = False


class ProviderError(AppError):
    """AI provider unavailable or failed."""
    code = "provider_error"
    status = 503
    recoverable = True


class UnsupportedLanguageError(AppError):
    """Language or language pair not supported."""
    code = "unsupported_language"
    status = 422
    recoverable = True


class FeatureDisabledError(AppError):
    """Feature flag disabled for this tenant/environment."""
    code = "feature_disabled"
    status = 403
    recoverable = False


class StorageError(AppError):
    """Object storage failure."""
    code = "storage_error"
    status = 502
    recoverable = True


class DocumentProcessingError(AppError):
    """Document could not be processed."""
    code = "document_processing_error"
    status = 422
    recoverable = True


def _envelope(code: str, message: str, recoverable: bool,
              details: Any = None, status: int = 500,
              headers: dict | None = None) -> JSONResponse:
    ctx = context.as_dict()
    return JSONResponse(
        status_code=status,
        headers=headers,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": ctx.get("request_id"),
                "trace_id": ctx.get("trace_id"),
                "recoverable": recoverable,
                "details": details or {},
            }
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        headers = {}
        if isinstance(exc, RateLimitError) and exc.details and "retry_after" in exc.details:
            headers["Retry-After"] = str(exc.details["retry_after"])
        return _envelope(exc.code, exc.message, exc.recoverable, exc.details,
                         exc.status, headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errs = exc.errors()
        first_msg = errs[0].get("msg") if errs else "Request validation failed"
        loc = errs[0].get("loc", []) if errs else []
        field_name = loc[-1] if loc else ""
        user_msg = f"{field_name}: {first_msg}" if (field_name and first_msg and first_msg != "Request validation failed") else (first_msg or "Request validation failed")
        details = {"errors": [
            {"loc": [str(p) for p in e.get("loc", [])], "msg": e.get("msg"),
             "type": e.get("type")}
            for e in errs[:20]
        ]}
        return _envelope("validation_error", user_msg,
                         True, details, 422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        recoverable = exc.status_code < 500
        return _envelope(f"http_{exc.status_code}", str(exc.detail),
                         recoverable, None, exc.status_code,
                         getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        import logging
        logging.getLogger("app.errors").exception("unhandled error", exc_info=exc)
        return _envelope("internal_error", "Internal server error", False, None, 500)
