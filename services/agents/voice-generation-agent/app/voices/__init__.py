"""Voice capabilities, consent, and selection for Agent 06."""
from app.voices.consent_manager import VoiceConsentManager
from app.voices.registry import VoiceRegistry
from app.voices.selector import VoiceSelector

__all__ = ["VoiceConsentManager", "VoiceRegistry", "VoiceSelector"]

