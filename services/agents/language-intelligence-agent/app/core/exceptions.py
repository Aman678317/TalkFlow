"""Domain exceptions for Language Intelligence Agent."""
from __future__ import annotations

from typing import Any, Dict, Optional


class LanguageIntelligenceError(Exception):
    """Base exception for all Language Intelligence Agent operations."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ProviderUnavailable(LanguageIntelligenceError):
    """Raised when a language detection provider cannot be loaded or is offline."""


class DetectionError(LanguageIntelligenceError):
    """Raised when language detection fails during execution."""


class TextValidationError(LanguageIntelligenceError):
    """Raised when incoming transcript text is malformed or invalid."""


class SessionCapacityExceededError(LanguageIntelligenceError):
    """Raised when concurrent session limit is breached."""
