"""Script detection and character ratio analyzer using Unicode patterns."""
from __future__ import annotations

from typing import Dict, Tuple
from app.language.scripts import SCRIPT_PATTERNS, detect_scripts


class ScriptDetector:
    """Analyzes character script distributions and identifies primary writing scripts."""

    @classmethod
    def analyze_script_distribution(cls, text: str) -> Dict[str, float]:
        """Calculates percentage distribution of alphabetic/syllabic scripts in text."""
        return detect_scripts(text)

    @classmethod
    def get_dominant_script(cls, text: str) -> Tuple[str, float]:
        """Returns primary ISO 15924 script and its proportion."""
        dist = cls.analyze_script_distribution(text)
        if not dist:
            return "Zyyy", 1.0
        primary_script, ratio = next(iter(dist.items()))
        return primary_script, ratio
