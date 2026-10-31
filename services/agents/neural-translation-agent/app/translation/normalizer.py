"""Text normalization and script cleaning for translation."""
from __future__ import annotations

import re
import unicodedata


def normalize_source_text(text: str) -> str:
    """NFC normalizes Unicode characters (critical for Devanagari matras) and collapses whitespace."""
    if not text:
        return ""
    # NFC normalization
    norm = unicodedata.normalize("NFC", text)
    # Collapse multiple spaces while preserving newline boundaries
    lines = norm.splitlines()
    cleaned_lines = [re.sub(r"[ \t]+", " ", line).strip() for line in lines]
    return "\n".join(line for line in cleaned_lines if line)

