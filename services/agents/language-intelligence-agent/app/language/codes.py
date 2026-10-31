"""ISO 639-1 and 639-3 language codes and alias mappings."""
from __future__ import annotations

from typing import Dict, Optional

# Canonical 2-letter ISO 639-1 to standard English name
LANGUAGE_NAMES: Dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "mr": "Marathi",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "gu": "Gujarati",
    "kn": "Kannada",
    "ml": "Malayalam",
    "pa": "Punjabi",
    "ur": "Urdu",
    "as": "Assamese",
    "or": "Odia",
    "sa": "Sanskrit",
    "ne": "Nepali",
    "sd": "Sindhi",
    "ks": "Kashmiri",
    "ja": "Japanese",
    "zh": "Chinese",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "ru": "Russian",
    "ar": "Arabic",
    "pt": "Portuguese",
    "it": "Italian",
    "ko": "Korean",
    "id": "Indonesian",
    "vi": "Vietnamese",
    "th": "Thai",
    "tr": "Turkish",
    "pl": "Polish",
    "nl": "Dutch",
    "sv": "Swedish",
    "da": "Danish",
    "fi": "Finnish",
    "no": "Norwegian",
    "el": "Greek",
    "he": "Hebrew",
    "und": "Undetermined",
}

# 3-letter ISO 639-2/3 to 2-letter ISO 639-1 mapping
ISO3_TO_ISO1: Dict[str, str] = {
    "eng": "en",
    "hin": "hi",
    "mar": "mr",
    "ben": "bn",
    "tam": "ta",
    "tel": "te",
    "guj": "gu",
    "kan": "kn",
    "mal": "ml",
    "pan": "pa",
    "urd": "ur",
    "asm": "as",
    "ori": "or",
    "san": "sa",
    "nep": "ne",
    "snd": "sd",
    "kas": "ks",
    "jpn": "ja",
    "zho": "zh",
    "chi": "zh",
    "spa": "es",
    "fra": "fr",
    "fre": "fr",
    "deu": "de",
    "ger": "de",
    "rus": "ru",
    "ara": "ar",
    "por": "pt",
    "ita": "it",
    "kor": "ko",
    "ind": "id",
    "vie": "vi",
    "tha": "th",
    "tur": "tr",
    "pol": "pl",
    "nld": "nl",
    "swe": "sv",
    "dan": "da",
    "fin": "fi",
    "nor": "no",
    "ell": "el",
    "heb": "he",
    "und": "und",
}


def normalize_language_code(code: Optional[str]) -> str:
    """Normalizes any incoming language code or tag into canonical 2-letter ISO 639-1."""
    if not code:
        return "und"

    clean = code.strip().lower()
    # Handle fastText __label__ prefix
    if clean.startswith("__label__"):
        clean = clean.replace("__label__", "")

    # Strip subtag if present (e.g. en-US -> en, hi-IN -> hi)
    clean = clean.split("-")[0].split("_")[0]

    # If 3-letter code, map to 2-letter code
    if len(clean) == 3 and clean in ISO3_TO_ISO1:
        return ISO3_TO_ISO1[clean]

    if clean in LANGUAGE_NAMES:
        return clean

    return clean if len(clean) == 2 else "und"


def get_language_name(code: str) -> str:
    norm = normalize_language_code(code)
    return LANGUAGE_NAMES.get(norm, f"Unknown ({norm})")


class LanguageCodes:
    NAMES = LANGUAGE_NAMES
    ISO3_MAP = ISO3_TO_ISO1

    @staticmethod
    def normalize_code(code: Optional[str]) -> str:
        return normalize_language_code(code)

    @staticmethod
    def get_name(code: str) -> str:
        return get_language_name(code)


