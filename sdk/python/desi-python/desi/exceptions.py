"""Typed exceptions for Desi Language AI and GlobalTalk AI."""

from typing import Optional, Dict, Any

class DesiError(Exception):
    """Base exception for all Desi and GlobalTalk AI client errors."""
    def __init__(self, message: str, code: Optional[str] = None, http_status: Optional[int] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.code = code or "client_error"
        self.http_status = http_status
        self.details = details or {}

class AuthenticationError(DesiError):
    """Raised when authentication fails (HTTP 401 or invalid API key)."""
    def __init__(self, message: str = "Invalid or missing API key.", **kwargs):
        super().__init__(message, code="unauthorized", http_status=401, **kwargs)

class ForbiddenError(DesiError):
    """Raised when access is forbidden (HTTP 403)."""
    def __init__(self, message: str = "Access forbidden.", **kwargs):
        super().__init__(message, code="forbidden", http_status=403, **kwargs)

class NotFoundError(DesiError):
    """Raised when a requested resource is not found (HTTP 404)."""
    def __init__(self, message: str = "Resource not found.", **kwargs):
        super().__init__(message, code="not_found", http_status=404, **kwargs)

class BadRequestError(DesiError):
    """Raised when invalid parameters or payload are sent (HTTP 400)."""
    def __init__(self, message: str = "Bad request.", **kwargs):
        super().__init__(message, code="bad_request", http_status=400, **kwargs)

class RateLimitError(DesiError):
    """Raised when request rate limits are exceeded (HTTP 429)."""
    def __init__(self, message: str = "Rate limit exceeded.", retry_after: Optional[int] = None, **kwargs):
        super().__init__(message, code="rate_limited", http_status=429, **kwargs)
        self.retry_after = retry_after

class QuotaExceededError(DesiError):
    """Raised when account character or document quota is exhausted (HTTP 402/429)."""
    def __init__(self, message: str = "Quota limit reached.", **kwargs):
        super().__init__(message, code="quota_exceeded", **kwargs)

class ServerError(DesiError):
    """Raised when the remote server returns a 5xx error."""
    def __init__(self, message: str = "Internal server error.", http_status: int = 500, **kwargs):
        super().__init__(message, code="server_error", http_status=http_status, **kwargs)
