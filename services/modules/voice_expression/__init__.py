"""TalkFlow Voice Expression, Prosody Preservation, and Consent Module."""
from modules.voice_expression.engine import VoiceExpressionEngine, voice_expression_engine
from modules.voice_expression.models import (
    AcousticFeatures,
    ConsentAuditEventType,
    DEFAULT_VOICE_CONFIG,
    DeliveryTag,
    ExpressiveSynthesisRequest,
    ExpressiveSynthesisResponse,
    PronunciationRule,
    ProsodyTransferPlan,
    SpeakerProsodyProfile,
    TalkFlowVoiceConfig,
    VoiceConsentAuditRecord,
    VoiceConsentRecord,
    VoiceEnrollmentRequest,
    VoiceGenerationMode,
)

__all__ = [
    "AcousticFeatures",
    "ConsentAuditEventType",
    "DEFAULT_VOICE_CONFIG",
    "DeliveryTag",
    "ExpressiveSynthesisRequest",
    "ExpressiveSynthesisResponse",
    "PronunciationRule",
    "ProsodyTransferPlan",
    "SpeakerProsodyProfile",
    "TalkFlowVoiceConfig",
    "VoiceConsentAuditRecord",
    "VoiceConsentRecord",
    "VoiceEnrollmentRequest",
    "VoiceExpressionEngine",
    "VoiceGenerationMode",
    "voice_expression_engine",
]
