"""Domain exceptions for Audio Synchronization & Delivery Agent (Agent 07)."""
from __future__ import annotations


class AudioDeliveryError(Exception):
    """Base exception for all Agent 07 errors."""


class ProvenanceValidationError(AudioDeliveryError):
    """Raised when audio metadata, identity bindings, or synthetic markers fail validation."""


class StaleUtteranceError(AudioDeliveryError):
    """Raised when an incoming audio chunk or utterance exceeds its conversational deadline."""


class DuplicateChunkError(AudioDeliveryError):
    """Raised when a redundant or already delivered chunk index arrives."""


class MissingChunkError(AudioDeliveryError):
    """Raised when an utterance reassembly deadline expires with missing sequence chunks."""


class RouteNotFoundError(AudioDeliveryError):
    """Raised when no active participant routes exist for a room or language group."""


class RoomIsolatedError(AudioDeliveryError):
    """Raised when a cross-room or cross-tenant delivery attempt is detected and blocked."""


class BargeInCancelledError(AudioDeliveryError):
    """Raised when an utterance is interrupted or cancelled by a newer conversational turn."""


class AudioFramingError(AudioDeliveryError):
    """Raised when binary wire framing (0x54 magic prefix) fails encoding or decoding."""


class MediaPublicationError(AudioDeliveryError):
    """Raised when media transport (WebRTC, LiveKit, WebSocket) fails to publish audio."""

