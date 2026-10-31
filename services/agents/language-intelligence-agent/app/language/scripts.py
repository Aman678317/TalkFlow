"""ISO 15924 Unicode script definitions and character range classifiers."""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

# Script patterns and ISO 15924 4-letter codes
SCRIPT_PATTERNS: List[Tuple[str, str, re.Pattern]] = [
    ("Devanagari", "Deva", re.compile(r"[\u0900-\u097F]")),
    ("Bengali", "Beng", re.compile(r"[\u0980-\u09FF]")),
    ("Tamil", "Taml", re.compile(r"[\u0B80-\u0BFF]")),
    ("Telugu", "Telu", re.compile(r"[\u0C00-\u0C7F]")),
    ("Gujarati", "Gujr", re.compile(r"[\u0A80-\u0AFF]")),
    ("Gurmukhi", "Guru", re.compile(r"[\u0A00-\u0A7F]")),
    ("Kannada", "Knda", re.compile(r"[\u0C80-\u0CFF]")),
    ("Malayalam", "Mlym", re.compile(r"[\u0D00-\u0D7F]")),
    ("Odia", "Orya", re.compile(r"[\u0B00-\u0B7F]")),
    ("Arabic", "Arab", re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")),
    ("Japanese", "Jpan", re.compile(r"[\u3040-\u309F\u30A0-\u30FF]")),  # Hiragana & Katakana
    ("Han", "Hani", re.compile(r"[\u4E00-\u9FFF]")),                   # Kanji / Hanzi
    ("Hangul", "Hang", re.compile(r"[\uAC00-\uD7AF]")),
    ("Cyrillic", "Cyrl", re.compile(r"[\u0400-\u04FF]")),
    ("Greek", "Grek", re.compile(r"[\u0370-\u03FF]")),
    ("Hebrew", "Hebr", re.compile(r"[\u0590-\u05FF]")),
    ("Thai", "Thai", re.compile(r"[\u0E00-\u0E7F]")),
    ("Latin", "Latn", re.compile(r"[a-zA-Z\u00C0-\u024F]")),
]


def detect_scripts(text: str) -> Dict[str, float]:
    """Calculates the proportion of Unicode characters belonging to each script.
    
    Returns a dict mapping ISO 15924 script codes (e.g. 'Deva', 'Latn') to their character ratio.
    """
    if not text:
        return {"Zyyy": 1.0}  # Common/Inherited script

    # Filter out whitespace and punctuation to measure letters
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return {"Zyyy": 1.0}

    total_letters = len(letters)
    script_counts: Dict[str, int] = {}

    for ch in letters:
        matched = False
        for name, code, pat in SCRIPT_PATTERNS:
            if pat.search(ch):
                script_counts[code] = script_counts.get(code, 0) + 1
                matched = True
                break
        if not matched:
            script_counts["Zyyy"] = script_counts.get("Zyyy", 0) + 1

    return {
        code: round(count / total_letters, 4)
        for code, count in sorted(script_counts.items(), key=lambda kv: -kv[1])
    }


def get_primary_script(text: str) -> str:
    """Returns the ISO 15924 4-letter code of the predominant script in text."""
    scripts = detect_scripts(text)
    if not scripts:
        return "Zyyy"
    return next(iter(scripts.keys()))
