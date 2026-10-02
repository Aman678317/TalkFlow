"""International Phone Number Service & E.164 Normalization.

Supports country codes, dialing validation, international formatting,
and carrier metadata across all major nations.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CountryDialInfo:
    country_code: str  # ISO 3166-1 alpha-2 (e.g. "IN", "JP", "US")
    name: str
    dial_code: str    # E.g. "+91", "+81", "+1"
    flag: str
    default_lang: str


COUNTRY_DIAL_REGISTRY: list[CountryDialInfo] = [
    CountryDialInfo("IN", "India", "+91", "🇮🇳", "hi"),
    CountryDialInfo("JP", "Japan", "+81", "🇯🇵", "ja"),
    CountryDialInfo("US", "United States", "+1", "🇺🇸", "en"),
    CountryDialInfo("CA", "Canada", "+1", "🇨🇦", "en"),
    CountryDialInfo("GB", "United Kingdom", "+44", "🇬🇧", "en"),
    CountryDialInfo("DE", "Germany", "+49", "🇩🇪", "de"),
    CountryDialInfo("FR", "France", "+33", "🇫🇷", "fr"),
    CountryDialInfo("ES", "Spain", "+34", "🇪🇸", "es"),
    CountryDialInfo("IT", "Italy", "+39", "🇮🇹", "it"),
    CountryDialInfo("RU", "Russia", "+7", "🇷🇺", "ru"),
    CountryDialInfo("BR", "Brazil", "+55", "🇧🇷", "pt"),
    CountryDialInfo("CN", "China", "+86", "🇨🇳", "zh"),
    CountryDialInfo("KR", "South Korea", "+82", "🇰🇷", "ko"),
    CountryDialInfo("SA", "Saudi Arabia", "+966", "🇸🇦", "ar"),
    CountryDialInfo("AE", "United Arab Emirates", "+971", "🇦🇪", "ar"),
    CountryDialInfo("AU", "Australia", "+61", "🇦🇺", "en"),
    CountryDialInfo("SG", "Singapore", "+65", "🇸🇬", "en"),
    CountryDialInfo("MX", "Mexico", "+52", "🇲🇽", "es"),
    CountryDialInfo("NL", "Netherlands", "+31", "🇳🇱", "nl"),
    CountryDialInfo("PL", "Poland", "+48", "🇵🇱", "pl"),
]

_COUNTRY_BY_CODE = {c.country_code: c for c in COUNTRY_DIAL_REGISTRY}
_E164_REGEX = re.compile(r"^\+[1-9]\d{6,14}$")


class PhoneNumberService:
    @staticmethod
    def get_supported_countries() -> list[dict]:
        """Return list of supported countries with dial codes and flags."""
        return [
            {
                "country_code": c.country_code,
                "name": c.name,
                "dial_code": c.dial_code,
                "flag": c.flag,
                "default_lang": c.default_lang,
            }
            for c in COUNTRY_DIAL_REGISTRY
        ]

    @staticmethod
    def normalize_to_e164(raw_number: str, default_country: str = "US") -> str:
        """Strip punctuation, whitespace and ensure canonical E.164 +CountryCodeNationalNumber format."""
        cleaned = re.sub(r"[^\d+]", "", raw_number.strip())
        if not cleaned:
            return ""

        if cleaned.startswith("+"):
            return cleaned

        # Handle 00 international prefix
        if cleaned.startswith("00"):
            return "+" + cleaned[2:]

        # If number lacks +, prepend dial code for default country
        info = _COUNTRY_BY_CODE.get(default_country.upper())
        dial_code = info.dial_code if info else "+1"
        return f"{dial_code}{cleaned.lstrip('0')}"

    @classmethod
    def validate_e164(cls, e164_number: str) -> tuple[bool, str | None]:
        """Validate if number strictly conforms to ITU-T E.164 standard (+ followed by 7-15 digits)."""
        if not e164_number:
            return False, "Phone number cannot be empty."
        if not e164_number.startswith("+"):
            return False, "International numbers must start with '+'."
        if not _E164_REGEX.match(e164_number):
            return False, "Invalid E.164 format. Expected + followed by 7-15 digits."
        return True, None

    @classmethod
    def detect_country(cls, e164_number: str) -> CountryDialInfo | None:
        """Detect country metadata matching the E.164 dial code prefix."""
        for c in sorted(COUNTRY_DIAL_REGISTRY, key=lambda x: len(x.dial_code), reverse=True):
            if e164_number.startswith(c.dial_code):
                return c
        return None

    @classmethod
    def format_friendly(cls, e164_number: str) -> str:
        """Format an E.164 string with international spaces for human readability."""
        country = cls.detect_country(e164_number)
        if not country:
            return e164_number
        rest = e164_number[len(country.dial_code):]
        if len(rest) == 10:
            return f"{country.flag} {country.dial_code} {rest[:5]} {rest[5:]}"
        elif len(rest) == 11:
            return f"{country.flag} {country.dial_code} {rest[:3]} {rest[3:7]} {rest[7:]}"
        return f"{country.flag} {country.dial_code} {rest}"
