"""Domain-specific exceptions for Speech Recognition Agent."""
from __future__ import annotations
from typing import Any, Dict, Optional


class STTAgentError(Exception):
    """Base exception for all speech recognition agent errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ProviderUnavailable(STTAgentError):
    """Raised when an STT provider is unavailable (weights missing, uninitialized, failing)."""

    def __init__(self, provider: str, reason: str):
        super().__init__(f"Provider {provider!r} unavailable: {reason}", {"provider": provider, "reason": reason})
        self.provider = provider
        self.reason = reason


class AudioValidationError(STTAgentError):
    """Raised when incoming audio fails format, channel, or duration validation."""


class TranscriptionError(STTAgentError):
    """Raised when a model fails to transcribe an audio segment."""


class SessionCapacityExceededError(STTAgentError):
    """Raised when concurrency limits or queue capacity is exceeded."""

