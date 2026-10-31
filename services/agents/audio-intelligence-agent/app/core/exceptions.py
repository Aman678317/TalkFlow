"""Domain exceptions for Audio Intelligence Agent."""
from __future__ import annotations


class AudioIntelligenceError(Exception):
    """Base exception for all Audio Intelligence Agent errors."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AudioValidationError(AudioIntelligenceError):
    """Raised when an incoming audio frame or payload fails validation."""
    pass


class UnsupportedAudioFormatError(AudioValidationError):
    """Raised when audio encoding, channels, or sample rate cannot be processed or converted."""
    pass


class CorruptedFrameError(AudioValidationError):
    """Raised when frame bytes are incomplete or misaligned."""
    pass


class SessionError(AudioIntelligenceError):
    """Base exception for audio session errors."""
    pass


class SessionNotFoundError(SessionError):
    """Raised when operation targets an unknown or expired session."""
    pass


class SessionCapacityExceededError(SessionError):
    """Raised when maximum concurrent sessions limit is reached."""
    pass


class QueueOverflowError(SessionError):
    """Raised when ingestion buffer reaches its bounded capacity under backpressure."""
    pass


class ProviderError(AudioIntelligenceError):
    """Base exception for audio processing providers (VAD, Denoise)."""
    pass


class VADProcessingError(ProviderError):
    """Raised when VAD inference or state calculation fails."""
    pass


class NoiseSuppressionError(ProviderError):
    """Raised when noise reduction algorithm encounters numerical or execution faults."""
    pass

