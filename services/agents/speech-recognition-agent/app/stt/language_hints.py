"""Language capability registry and code-switching / Hinglish handling."""
from __future__ import annotations

from typing import Dict, List, Optional
from app.models.schemas import LanguageCapability


class LanguageRegistry:
    """Registry of verified languages, Indian languages, and code-switching capabilities."""

    _CAPABILITIES: Dict[str, LanguageCapability] = {
        "en": LanguageCapability(
            code="en", name="English", provider="faster-whisper", model="base",
            available=True, evaluation_status="production_verified", code_switch_supported=True,
        ),
        "hi": LanguageCapability(
            code="hi", name="Hindi", provider="faster-whisper", model="base",
            available=True, evaluation_status="production_verified", code_switch_supported=True,
        ),
        "mr": LanguageCapability(
            code="mr", name="Marathi", provider="faster-whisper", model="base",
            available=True, evaluation_status="verified", code_switch_supported=True,
        ),
        "bn": LanguageCapability(
            code="bn", name="Bengali", provider="faster-whisper", model="base",
            available=True, evaluation_status="verified", code_switch_supported=True,
        ),
        "ta": LanguageCapability(
            code="ta", name="Tamil", provider="faster-whisper", model="base",
            available=True, evaluation_status="verified", code_switch_supported=True,
        ),
        "te": LanguageCapability(
            code="te", name="Telugu", provider="faster-whisper", model="base",
            available=True, evaluation_status="verified", code_switch_supported=True,
        ),
        "gu": LanguageCapability(
            code="gu", name="Gujarati", provider="faster-whisper", model="base",
            available=True, evaluation_status="verified", code_switch_supported=True,
        ),
        "kn": LanguageCapability(
            code="kn", name="Kannada", provider="faster-whisper", model="base",
            available=True, evaluation_status="verified", code_switch_supported=True,
        ),
        "ml": LanguageCapability(
            code="ml", name="Malayalam", provider="faster-whisper", model="base",
            available=True, evaluation_status="verified", code_switch_supported=True,
        ),
        "pa": LanguageCapability(
            code="pa", name="Punjabi", provider="faster-whisper", model="base",
            available=True, evaluation_status="verified", code_switch_supported=True,
        ),
        "ur": LanguageCapability(
            code="ur", name="Urdu", provider="faster-whisper", model="base",
            available=True, evaluation_status="verified", code_switch_supported=True,
        ),
        "ja": LanguageCapability(
            code="ja", name="Japanese", provider="faster-whisper", model="base",
            available=True, evaluation_status="verified", code_switch_supported=False,
        ),
        "zh": LanguageCapability(
            code="zh", name="Chinese", provider="faster-whisper", model="base",
            available=True, evaluation_status="verified", code_switch_supported=False,
        ),
        "es": LanguageCapability(
            code="es", name="Spanish", provider="faster-whisper", model="base",
            available=True, evaluation_status="verified", code_switch_supported=True,
        ),
        "fr": LanguageCapability(
            code="fr", name="French", provider="faster-whisper", model="base",
            available=True, evaluation_status="verified", code_switch_supported=True,
        ),
        "de": LanguageCapability(
            code="de", name="German", provider="faster-whisper", model="base",
            available=True, evaluation_status="verified", code_switch_supported=True,
        ),
    }

    # Common code-switching and technical prompts to preserve Hinglish
    HINGLISH_PROMPTS = [
        "meeting mein AI discuss karenge",
        "production ready code",
        "client presentation",
        "feature implementation",
    ]

    @classmethod
    def get_capabilities(cls) -> List[LanguageCapability]:
        """Returns list of all registered language capabilities."""
        return list(cls._CAPABILITIES.values())

    @classmethod
    def get_capability(cls, lang_code: str) -> Optional[LanguageCapability]:
        """Returns language capability for given code or None."""
        clean = lang_code.split("-")[0].lower()
        return cls._CAPABILITIES.get(clean)

    @classmethod
    def is_supported(cls, lang_code: str) -> bool:
        clean = lang_code.split("-")[0].lower()
        return clean in cls._CAPABILITIES

    @classmethod
    def extract_language_hint(cls, detected_code: str, prob: float) -> tuple[str, float]:
        """Extracts and formats language hint without overriding Agent 03."""
        code = detected_code.split("-")[0].lower()
        if code in cls._CAPABILITIES:
            return code, round(prob, 3)
        return "en", round(prob, 3)

