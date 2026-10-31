"""Audio Quality & Confidence Audit Engine (Module G).

Tracks per-segment transcription confidence, translation quality gates, TTS synthesis telemetry,
detects uncertain words and phrases, and manages manual review workflows.
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from modules.quality_confidence.models import SegmentQualityAudit, UncertainSpan

logger = logging.getLogger("talkflow.modules.quality_confidence")


class QualityConfidenceEngine:
    """Audit ledger for segment-level quality, uncertainty detection, and human review."""

    def __init__(self) -> None:
        # segment_id -> SegmentQualityAudit
        self._audits: Dict[str, SegmentQualityAudit] = {}

    def record_audit(self, audit: SegmentQualityAudit) -> SegmentQualityAudit:
        """Stores or updates a segment quality audit record."""
        if not audit.audit_id:
            audit.audit_id = f"audit_{hashlib.md5(f'{audit.segment_id}_{time.time()}'.encode()).hexdigest()[:10]}"
        self._audits[audit.segment_id] = audit
        return audit

    def get_audit(self, segment_id: str) -> Optional[SegmentQualityAudit]:
        return self._audits.get(segment_id)

    def list_audits(self, limit: int = 50, requires_review_only: bool = False) -> List[SegmentQualityAudit]:
        """Lists segment audits, optionally filtering for items flagged for human review."""
        results = []
        for a in self._audits.values():
            if requires_review_only and a.quality_decision not in ("REJECT", "MANUAL_REVIEW", "ACCEPT_WITH_WARNINGS"):
                continue
            results.append(a)
        return results[:limit]

    def analyze_whisper_uncertainty(
        self,
        segment_id: str,
        text: str,
        words_timing: List[Dict[str, Any]],
        overall_confidence: float,
        quality_flags: Optional[List[str]] = None,
        threshold: float = 0.50,
    ) -> Tuple[bool, List[UncertainSpan]]:
        """Identifies uncertain words from word timestamps without fabricating confidence."""
        flags = quality_flags or []
        uncertain_spans = []

        for w in words_timing:
            conf = float(w.get("confidence", overall_confidence))
            if conf < threshold:
                uncertain_spans.append(
                    UncertainSpan(
                        text=str(w.get("word", "")).strip(),
                        start_ms=int(round(float(w.get("start", 0.0)) * 1000)),
                        end_ms=int(round(float(w.get("end", 0.0)) * 1000)),
                        confidence=round(conf, 3),
                        reason="acoustic_uncertainty",
                    )
                )

        has_uncertainty = len(uncertain_spans) > 0 or ("low_confidence" in flags)
        return has_uncertainty, uncertain_spans

    def submit_manual_correction(
        self,
        segment_id: str,
        corrected_text: str,
        reviewed_by: str = "human_editor",
    ) -> Optional[SegmentQualityAudit]:
        """Applies manual correction to a segment audit record."""
        audit = self._audits.get(segment_id)
        if not audit:
            return None

        audit.is_manually_corrected = True
        audit.corrected_text = corrected_text.strip()
        audit.translated_text = corrected_text.strip()
        audit.reviewed_by = reviewed_by
        audit.quality_decision = "ACCEPT"
        audit.quality_score = 1.0
        audit.quality_flags = [f for f in audit.quality_flags if f not in ("low_confidence", "high_no_speech_prob")]
        audit.has_acoustic_uncertainty = False

        logger.info(f"Manual correction applied to segment '{segment_id}' by '{reviewed_by}'")
        return audit


# Global Quality Confidence Instance
quality_confidence_engine = QualityConfidenceEngine()

