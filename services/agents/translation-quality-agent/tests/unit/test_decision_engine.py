"""Unit tests for QualityScorer and DecisionEngine."""
from __future__ import annotations

import pytest
from app.models.schemas import IssueSeverity, QualityCategory, QualityDecision, QualityIssue
from app.quality.decision_engine import DecisionEngine
from app.quality.scorer import QualityScorer


def test_accept_decision():
    """Translations with high scores and no issues should be ACCEPTed."""
    decision, status, retry = DecisionEngine.resolve_decision(
        overall_score=0.92,
        issues=[],
        has_critical_error=False,
        current_retry_count=0,
    )
    assert decision == QualityDecision.ACCEPT
    assert status == "passed"
    assert retry is None


def test_accept_with_warnings_decision():
    """Translations with minor issues or borderline scores should be ACCEPT_WITH_WARNINGS."""
    minor_issue = QualityIssue(
        code="formatting_warning",
        category=QualityCategory.FORMATTING,
        severity=IssueSeverity.MINOR,
        description="Minor punctuation variance",
    )
    decision, status, retry = DecisionEngine.resolve_decision(
        overall_score=0.88,
        issues=[minor_issue],
        has_critical_error=False,
    )
    assert decision == QualityDecision.ACCEPT_WITH_WARNINGS
    assert status == "warning"
    assert retry is None


def test_critical_error_triggers_retry():
    """Critical integrity errors must recommend alternate provider if retry budget permits."""
    critical_issue = QualityIssue(
        code="number_mismatch",
        category=QualityCategory.DATA_INTEGRITY,
        severity=IssueSeverity.CRITICAL,
        description="Critical number missing or corrupted",
    )
    decision, status, retry = DecisionEngine.resolve_decision(
        overall_score=0.30,
        issues=[critical_issue],
        has_critical_error=True,
        current_retry_count=0,
        current_provider="argos",
        source_lang="en",
        target_lang="hi",
    )
    assert decision == QualityDecision.RETRY_WITH_ALTERNATE_PROVIDER
    assert status == "failed"
    assert retry is not None
    assert retry["alternate_provider_required"] is True
    assert retry["recommended_provider"] == "marian"
    assert retry["current_retry_count"] == 1


def test_critical_error_retries_exhausted_reject():
    """When retries are exhausted, critical integrity errors must lead to REJECT."""
    critical_issue = QualityIssue(
        code="negation_reversal",
        category=QualityCategory.DATA_INTEGRITY,
        severity=IssueSeverity.CRITICAL,
        description="Polarity reversed",
    )
    decision, status, retry = DecisionEngine.resolve_decision(
        overall_score=0.25,
        issues=[critical_issue],
        has_critical_error=True,
        current_retry_count=2,  # retry budget is 2
    )
    assert decision == QualityDecision.REJECT
    assert status == "failed"
    assert retry is None


def test_major_error_holds_for_human_when_retries_exhausted():
    """Major terminology errors should hold for human review once retries are exhausted."""
    major_issue = QualityIssue(
        code="terminology_missing",
        category=QualityCategory.TERMINOLOGY,
        severity=IssueSeverity.MAJOR,
        description="Mandatory glossary term missing",
    )
    decision, status, retry = DecisionEngine.resolve_decision(
        overall_score=0.65,
        issues=[major_issue],
        has_critical_error=False,
        current_retry_count=2,
    )
    assert decision == QualityDecision.HOLD_FOR_HUMAN
    assert status == "warning"
    assert retry is None


def test_hard_safety_gate_score_ceiling():
    """A critical error must cap composite quality score at <= 0.35 regardless of high fluency."""
    critical_issue = QualityIssue(
        code="currency_mismatch",
        category=QualityCategory.DATA_INTEGRITY,
        severity=IssueSeverity.CRITICAL,
        description="Currency symbol corrupted",
    )
    # Even with 1.0 semantic accuracy and 1.0 integrity input
    composite, scores = QualityScorer.calculate_scores(
        semantic_score=1.0,
        data_integrity_score=1.0,
        issues=[critical_issue],
        has_critical_error=True,
    )
    assert composite <= 0.35, f"Expected composite <= 0.35 under critical error, got {composite}"
    assert scores["data_integrity"] == 1.0
