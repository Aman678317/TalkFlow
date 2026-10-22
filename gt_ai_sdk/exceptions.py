"""SDK Exception hierarchy — mirrors ``errors.py`` in the server but
is importable standalone (no FastAPI / SQLAlchemy dependency).

Hierarchy::

    GlobalTalkError                 ← base
    ├── AuthenticationError         ← 401 / invalid API key
    ├── QuotaExceededError          ← 429 / character or minute quota
    ├── UnsupportedLanguageError    ← 400 / language pair not supported
    ├── TranslationError            ← 422 / translation pipeline failure
    ├── DocumentError               ← 422 / document processing failure
    └── NetworkError                ← connection / timeout issues
"""
from __future__ import annotations

from typing import Any


class GlobalTalkError(Exception):
    """Base exception for all GlobalTalk AI SDK errors."""

    def __init__(
        self,
        message: str = "",
        *,
        code: str = "error",
        status: int = 500,
        recoverable: bool = False,
        details: Any = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.recoverable = recoverable
        self.details = details
        self.request_id = request_id

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"code={self.code!r}, status={self.status}, "
            f"message={self.message!r})"
        )


class AuthenticationError(GlobalTalkError):
    """Invalid or missing API key / JWT token."""

    def __init__(self, message: str = "Authentication failed", **kw: Any) -> None:
        super().__init__(message, code="auth_error", status=401, **kw)


class QuotaExceededError(GlobalTalkError):
    """Character count or realtime-minutes quota exceeded."""

    def __init__(self, message: str = "Quota exceeded", **kw: Any) -> None:
        super().__init__(message, code="quota_exceeded", status=429,
                         recoverable=True, **kw)


class UnsupportedLanguageError(GlobalTalkError):
    """The requested language pair is not supported.

    ``recoverable=True`` because the caller can fall back to a pivot language
    or pass-through mode.
    """

    def __init__(
        self,
        source_lang: str = "",
        target_lang: str = "",
        message: str = "",
        **kw: Any,
    ) -> None:
        msg = message or f"Language pair not supported: {source_lang!r} → {target_lang!r}"
        super().__init__(msg, code="unsupported_language", status=400,
                         recoverable=True, **kw)
        self.source_lang = source_lang
        self.target_lang = target_lang


class TranslationError(GlobalTalkError):
    """The translation pipeline failed.

    Raised when every model in the fallback chain reports
    ``ProviderUnavailable`` and no pass-through is allowed.
    """

    def __init__(self, message: str = "Translation failed", **kw: Any) -> None:
        super().__init__(message, code="translation_failed", status=422, **kw)


class DocumentError(GlobalTalkError):
    """Document parsing or reconstruction failed."""

    def __init__(self, message: str = "Document processing failed", **kw: Any) -> None:
        super().__init__(message, code="document_error", status=422, **kw)


class NetworkError(GlobalTalkError):
    """HTTP connection / timeout error when reaching the GlobalTalk API."""

    def __init__(self, message: str = "Network error", **kw: Any) -> None:
        super().__init__(message, code="network_error", status=503,
                         recoverable=True, **kw)
