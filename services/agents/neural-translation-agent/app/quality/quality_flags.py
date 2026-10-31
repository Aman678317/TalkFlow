"""Quality flags returned alongside translation results."""
from __future__ import annotations

from enum import StrEnum


class QualityFlag(StrEnum):
    EMPTY_TRANSLATION = "empty_translation"
    NUMBER_MISMATCH = "number_mismatch"
    URL_OR_EMAIL_LOST = "url_or_email_lost"
    SUSPICIOUSLY_LONG = "suspiciously_long"
    SUSPICIOUSLY_SHORT = "suspiciously_short"
    SCRIPT_LOST = "script_lost"
    UNTRANSLATED_OUTPUT = "untranslated_output"
    GLOSSARY_TERM_MISSING = "glossary_term_missing"
    PROTECTED_SPAN_CORRUPTED = "protected_span_corrupted"
    PIVOTED_TRANSLATION = "pivoted_via_intermediate"
    SOURCE_EQUALS_TARGET = "source_equals_target"
    DEV_PROVIDER = "dev_provider"
    FALLBACK_PROVIDER = "fallback_provider"

