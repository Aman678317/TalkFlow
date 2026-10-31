"""Custom exception hierarchy for Neural Translation Agent."""
from __future__ import annotations


class TranslationAgentError(Exception):
    """Base exception for all Translation Agent errors."""


class UnsupportedLanguageError(TranslationAgentError):
    """Raised when source or target language is not supported."""


class UnsupportedLanguagePairError(TranslationAgentError):
    """Raised when a specific source->target pair cannot be translated."""


class ProviderUnavailableError(TranslationAgentError):
    """Raised when a translation provider or model is offline or uninstalled."""


class PrivacyViolationError(TranslationAgentError):
    """Raised when an external online provider is invoked for a private-only request."""


class ValidationError(TranslationAgentError):
    """Raised when input text or metadata violates limits or constraints."""


class OutputIntegrityError(TranslationAgentError):
    """Raised when translated text fails essential integrity checks."""


class TranslationTimeoutError(TranslationAgentError):
    """Raised when translation inference breaches latency deadline."""

