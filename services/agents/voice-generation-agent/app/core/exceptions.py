"""Domain exceptions for Voice Generation Agent."""
from __future__ import annotations


class VoiceGenerationError(Exception):
    """Base exception for all Agent 06 voice generation errors."""


class QualityGateRejectedError(VoiceGenerationError):
    """Raised when synthesis is requested on a translation that failed Agent 05's quality gate."""


class TranslationIdentityMismatchError(VoiceGenerationError):
    """Raised when translation identity (conversation/segment/translation ID) is missing or mismatched."""


class UnsupportedLanguageError(VoiceGenerationError):
    """Raised when the requested target language has no verified compatible voice."""


class VoiceUnavailableError(VoiceGenerationError):
    """Raised when the specified voice is not installed or available on this deployment."""


class PrivacyViolationError(VoiceGenerationError):
    """Raised when external provider invocation is attempted under private_only or offline_only policies."""


class ConsentRequiredError(VoiceGenerationError):
    """Raised when voice cloning or preservation is attempted without verified opt-in consent."""


class ConsentRevokedError(VoiceGenerationError):
    """Raised when voice consent was previously granted but has since been revoked."""


class ProviderUnavailableError(VoiceGenerationError):
    """Raised when a specific TTS provider or model weight is unavailable."""


class SpeechSynthesisError(VoiceGenerationError):
    """Raised when speech synthesis fails in the underlying audio engine."""


class AudioFramingError(VoiceGenerationError):
    """Raised when binary audio framing fails encoding or decoding."""


class ProviderTimeoutError(VoiceGenerationError):
    """Raised when a TTS provider fails to return audio within the configured deadline."""


class SynthesisCancelledError(VoiceGenerationError):
    """Raised when an active synthesis request is cancelled by user barge-in or session termination."""
