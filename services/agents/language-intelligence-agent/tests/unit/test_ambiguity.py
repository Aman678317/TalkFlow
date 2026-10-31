"""Unit tests for Ambiguity and Short-Text Rejection Engine."""
import pytest
from app.detection.ambiguity import AmbiguityDetector
from app.models.schemas import CandidateLanguage


def test_short_text_rejection():
    detector = AmbiguityDetector(min_length_chars=3)
    is_ambig, status, reason = detector.evaluate_ambiguity(
        text="Hi",
        primary_lang="en",
        confidence=0.90,
        candidates=[],
        spans=[],
    )
    assert is_ambig is True
    assert status == "ambiguous"
    assert reason == "text_too_short"


def test_low_confidence_rejection():
    detector = AmbiguityDetector(confidence_threshold=0.45)
    is_ambig, status, reason = detector.evaluate_ambiguity(
        text="Some uncertain noisy acoustic transcript",
        primary_lang="nl",
        confidence=0.25,
        candidates=[],
        spans=[],
    )
    assert is_ambig is True
    assert status == "insufficient_confidence"
    assert reason == "low_confidence_threshold"

