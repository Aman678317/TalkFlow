"""Unit tests for Agent 06 Quality Gate validation."""
import pytest
from app.core.exceptions import QualityGateRejectedError
from app.gate.quality_gate import QualityGateValidator


def test_quality_gate_accept():
    gate = QualityGateValidator(min_score=0.40)
    # Should not raise
    gate.validate_decision("ACCEPT", score=0.92, segment_id="seg_01")
    gate.validate_decision("ACCEPT_WITH_WARNINGS", score=0.65, segment_id="seg_02")


def test_quality_gate_reject():
    gate = QualityGateValidator(min_score=0.40)
    with pytest.raises(QualityGateRejectedError) as exc_info:
        gate.validate_decision("REJECT", score=0.30, segment_id="seg_03")
    assert "REJECT" in str(exc_info.value)

    with pytest.raises(QualityGateRejectedError):
        gate.validate_decision("HOLD_FOR_HUMAN", score=0.75, segment_id="seg_04")

    with pytest.raises(QualityGateRejectedError):
        gate.validate_decision("RETRY_WITH_ALTERNATE_PROVIDER", score=0.55, segment_id="seg_05")


def test_quality_gate_low_score_rejection():
    gate = QualityGateValidator(min_score=0.40)
    with pytest.raises(QualityGateRejectedError) as exc_info:
        gate.validate_decision("ACCEPT", score=0.25, segment_id="seg_06")
    assert "below minimum threshold" in str(exc_info.value)

