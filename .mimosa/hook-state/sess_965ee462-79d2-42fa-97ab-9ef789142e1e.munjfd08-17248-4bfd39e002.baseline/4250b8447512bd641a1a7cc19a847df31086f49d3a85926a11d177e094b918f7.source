"""BCP-47 language code normalization for voice/speech APIs.

Chrome's SpeechRecognition and the Web Speech API are strict about BCP-47
format. This module normalises the various code formats used internally
(ISO 639-1 + ISO 3166-1 alpha-2) into the exact strings the browser accepts.

Usage::

    from gt_ai.voice.bcp47 import to_bcp47

    to_bcp47("en")      # → "en-US"
    to_bcp47("EN")      # → "en-US"
    to_bcp47("zh")      # → "zh-CN"
    to_bcp47("en-GB")   # → "en-GB"  (already valid, pass-through)
    to_bcp47("unknown") # → "en-US"  (safe fallback)
"""
from __future__ import annotations

import re

# Primary BCP-47 mappings — extended for GlobalTalk's supported language matrix.
# Key: ISO 639-1 code (lowercase).  Value: canonical BCP-47 tag for STT.
_LANG_TO_BCP47: dict[str, str] = {
    "af": "af-ZA",
    "ar": "ar-SA",
    "bg": "bg-BG",
    "bn": "bn-BD",
    "ca": "ca-ES",
    "cs": "cs-CZ",
    "cy": "cy-GB",
    "da": "da-DK",
    "de": "de-DE",
    "el": "el-GR",
    "en": "en-US",
    "es": "es-ES",
    "et": "et-EE",
    "fa": "fa-IR",
    "fi": "fi-FI",
    "fr": "fr-FR",
    "ga": "ga-IE",
    "gl": "gl-ES",
    "gu": "gu-IN",
    "he": "he-IL",
    "hi": "hi-IN",
    "hr": "hr-HR",
    "hu": "hu-HU",
    "hy": "hy-AM",
    "id": "id-ID",
    "is": "is-IS",
    "it": "it-IT",
    "ja": "ja-JP",
    "ka": "ka-GE",
    "kn": "kn-IN",
    "ko": "ko-KR",
    "lt": "lt-LT",
    "lv": "lv-LV",
    "mk": "mk-MK",
    "ml": "ml-IN",
    "mr": "mr-IN",
    "ms": "ms-MY",
    "mt": "mt-MT",
    "nb": "nb-NO",
    "nl": "nl-NL",
    "pa": "pa-IN",
    "pl": "pl-PL",
    "pt": "pt-PT",
    "ro": "ro-RO",
    "ru": "ru-RU",
    "sk": "sk-SK",
    "sl": "sl-SI",
    "sq": "sq-AL",
    "sr": "sr-RS",
    "sv": "sv-SE",
    "sw": "sw-KE",
    "ta": "ta-IN",
    "te": "te-IN",
    "th": "th-TH",
    "tr": "tr-TR",
    "uk": "uk-UA",
    "ur": "ur-PK",
    "vi": "vi-VN",
    "zh": "zh-CN",
}

# Overrides for common regional variants
_REGION_OVERRIDES: dict[str, str] = {
    "en-gb":  "en-GB",
    "en-au":  "en-AU",
    "en-in":  "en-IN",
    "es-mx":  "es-MX",
    "es-419": "es-419",
    "fr-ca":  "fr-CA",
    "fr-be":  "fr-BE",
    "pt-br":  "pt-BR",
    "zh-tw":  "zh-TW",
    "zh-hk":  "zh-HK",
}

_BCP47_RE = re.compile(r"^[a-z]{2,3}(-[A-Z]{2,3})?$")
_FALLBACK = "en-US"


def to_bcp47(lang_code: str) -> str:
    """Normalize a language code to a valid BCP-47 tag.

    Args:
        lang_code:  Language code in any supported format:
                    ISO 639-1 (``"en"``), ISO 639-1 + region (``"en-US"``),
                    or uppercase variants (``"EN"``, ``"EN-US"``).

    Returns:
        A canonical BCP-47 tag accepted by browser SpeechRecognition APIs.
        Falls back to ``"en-US"`` if the code is unrecognized.
    """
    if not lang_code or not isinstance(lang_code, str):
        return _FALLBACK

    normalized = lang_code.strip().lower()

    # Already a valid "ll-RR" tag → pass through with correct casing
    if "-" in normalized:
        override = _REGION_OVERRIDES.get(normalized)
        if override:
            return override
        # Generic: "en-us" → "en-US"
        parts = normalized.split("-", 1)
        if len(parts) == 2:
            tag = f"{parts[0]}-{parts[1].upper()}"
            if _BCP47_RE.match(tag):
                return tag

    # ISO 639-1 base code lookup
    base = normalized.split("-")[0]
    if base in _LANG_TO_BCP47:
        return _LANG_TO_BCP47[base]

    return _FALLBACK


def is_supported(lang_code: str) -> bool:
    """Return ``True`` if ``lang_code`` maps to a known BCP-47 tag."""
    base = lang_code.strip().lower().split("-")[0]
    return base in _LANG_TO_BCP47
