"""TalkFlow Language Capability Integration and Verification Adapter."""
from __future__ import annotations

from typing import Any, Dict, List
from app.language.codes import get_language_name, normalize_language_code

# TalkFlow production and experimental translation capabilities
TALKFLOW_PRODUCTION_LANGUAGES = {
    "en", "hi", "mr", "bn", "ta", "te", "gu", "kn", "ml", "pa", "ur",
    "ja", "zh", "es", "fr", "de", "ru", "ar", "pt", "it", "ko",
}

TALKFLOW_EXPERIMENTAL_LANGUAGES = {
    "as", "or", "sa", "ne", "id", "vi", "th", "tr", "pl", "nl", "sv", "da", "fi", "no", "el", "he",
}


class LanguageCapabilityAdapter:
    """Verifies detected language against TalkFlow's operational translation capabilities."""

    @classmethod
    def get_status(cls, lang_code: str) -> Dict[str, Any]:
        """Evaluates whether the language has downstream translation support in TalkFlow."""
        code = normalize_language_code(lang_code)

        if code in TALKFLOW_PRODUCTION_LANGUAGES:
            return {
                "language": code,
                "name": get_language_name(code),
                "capability": "production",
                "stt_supported": True,
                "mt_supported": True,
                "routing_recommendation": "direct_translation",
            }
        elif code in TALKFLOW_EXPERIMENTAL_LANGUAGES:
            return {
                "language": code,
                "name": get_language_name(code),
                "capability": "experimental",
                "stt_supported": True,
                "mt_supported": True,
                "routing_recommendation": "experimental_translation",
            }
        elif code == "und":
            return {
                "language": "und",
                "name": "Undetermined",
                "capability": "unsupported",
                "stt_supported": False,
                "mt_supported": False,
                "routing_recommendation": "request_clarification",
            }
        else:
            return {
                "language": code,
                "name": get_language_name(code),
                "capability": "unsupported",
                "stt_supported": False,
                "mt_supported": False,
                "routing_recommendation": "honest_degradation_passthrough",
            }

    @classmethod
    def check_language_support(cls, lang_code: str) -> Dict[str, Any]:
        return cls.get_status(lang_code)

    @classmethod
    def list_all_capabilities(cls) -> List[Dict[str, Any]]:
        """Returns the full catalog of evaluated language capabilities."""
        all_codes = sorted(list(TALKFLOW_PRODUCTION_LANGUAGES | TALKFLOW_EXPERIMENTAL_LANGUAGES))
        return [cls.get_status(code) for code in all_codes]


TalkFlowCapabilityRegistry = LanguageCapabilityAdapter
