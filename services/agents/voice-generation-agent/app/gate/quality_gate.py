"""Hard quality gate enforcing Agent 05 translation approval."""
from __future__ import annotations

import logging
from typing import Optional
from app.core.exceptions import QualityGateRejectedError

log = logging.getLogger("agent06.gate.quality")

ALLOWED_DECISIONS = {"ACCEPT", "ACCEPT_WITH_WARNINGS"}
DISALLOWED_DECISIONS = {"REJECT", "HOLD_FOR_HUMAN", "RETRY_WITH_ALTERNATE_PROVIDER"}


class QualityGateValidator:
    """Enforces that only translations explicitly approved by Agent 05 can reach speech synthesis."""

    def __init__(self, min_score: float = 0.40) -> None:
        self.min_score = min_score

    def validate_decision(
        self,
        decision: str,
        score: Optional[float] = None,
        quality_score: Optional[float] = None,
        translation_id: Optional[str] = None,
        segment_id: Optional[str] = None,
    ) -> bool:
        """Validates that Agent 05 issued an acceptable quality decision."""
        eff_score = score if score is not None else (quality_score if quality_score is not None else 1.0)
        dec = (decision or "").strip().upper()
        if not dec:
            raise QualityGateRejectedError(
                f"Missing Agent 05 quality approval for translation '{translation_id or segment_id}'. "
                "Speech generation cannot proceed without verified quality assessment."
            )

        if dec in DISALLOWED_DECISIONS or dec not in ALLOWED_DECISIONS:
            log.warning(
                f"[Quality Gate Rejected] Translation '{translation_id or segment_id}' has decision '{dec}' "
                f"(score={eff_score}). Synthesis blocked."
            )
            raise QualityGateRejectedError(
                f"Translation '{translation_id or segment_id}' was NOT approved by Agent 05: decision='{dec}'. "
                "Speech synthesis is strictly prohibited on unapproved, held, or retry-recommended translations."
            )

        if eff_score < self.min_score:
            raise QualityGateRejectedError(
                f"Translation '{translation_id or segment_id}' score {eff_score} is below minimum threshold {self.min_score}."
            )

        return True


quality_gate = QualityGateValidator()
