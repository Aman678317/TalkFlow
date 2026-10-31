"""Core configuration, logging, and exceptions."""
from app.core.config import settings
from app.core.exceptions import (
    ConsentRequiredError,
    PrivacyViolationError,
    ProviderTimeoutError,
    QualityGateRejectedError,
    SynthesisCancelledError,
    TranslationIdentityMismatchError,
    UnsupportedLanguageError,
    VoiceGenerationError,
    VoiceUnavailableError,
)
from app.core.logging import get_logger

__all__ = [
    "settings",
    "get_logger",
    "VoiceGenerationError",
    "QualityGateRejectedError",
    "TranslationIdentityMismatchError",
    "UnsupportedLanguageError",
    "VoiceUnavailableError",
    "PrivacyViolationError",
    "ConsentRequiredError",
    "ProviderTimeoutError",
    "SynthesisCancelledError",
]

