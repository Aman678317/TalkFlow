"""Ambiguity, short-text and uncertainty detector for fail-closed honest reporting."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from app.core.config import settings
from app.models.schemas import CandidateLanguage, DetectionResult, LanguageSpan


class AmbiguityDetector:
    """Evaluates whether transcript text has sufficient signal for reliable language classification."""

    def __init__(
        self,
        min_length_chars: int = 3,
        confidence_threshold: float = 0.45,
        uncertainty_margin: float = 0.15,
    ):
        self.min_length_chars = min_length_chars
        self.confidence_threshold = confidence_threshold
        self.uncertainty_margin = uncertainty_margin

    def evaluate_ambiguity(
        self,
        text: str,
        primary_lang: str,
        confidence: float,
        candidates: List[CandidateLanguage],
        spans: List[LanguageSpan],
    ) -> Tuple[bool, str, Optional[str]]:
        """Returns (is_ambiguous, detection_status, reason_code).
        detection_status: 'success' | 'ambiguous' | 'insufficient_confidence'
        """
        clean_text = text.strip()

        # 1. Extremely Short Text Check (< 3 characters)
        if len(clean_text) < self.min_length_chars:
            return True, "ambiguous", "text_too_short"

        # Check if high-quality code-switching spans exist
        known_span_langs = {s.language for s in spans if s.language not in ("und", "Zyyy")}
        is_code_switched = len(known_span_langs) >= 2

        # 2. Insufficient Confidence Threshold (< 0.45)
        # In multi-language code-switching, individual language score is divided, so evaluate composite
        if not is_code_switched:
            if confidence < self.confidence_threshold or primary_lang == "und":
                return True, "insufficient_confidence", "low_confidence_threshold"

        # 3. Conflicting Top Candidates with negligible margin (only if NOT valid code-switching)
        if not is_code_switched and candidates:
            second_prob = candidates[0].confidence
            if (confidence - second_prob) < self.uncertainty_margin and confidence < 0.60:
                return True, "ambiguous", f"conflicting_candidates_{primary_lang}_vs_{candidates[0].language}"

        # 4. Spans check
        if spans:
            unique_langs = {s.language for s in spans if s.language != "und"}
            if not unique_langs and len(clean_text) > 8:
                return True, "ambiguous", "all_spans_undetermined"

        return False, "success", None
