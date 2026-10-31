"""Accuracy and regression test suite using TalkFlow golden datasets."""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from app.models.schemas import EvaluationRequestSchema, QualityDecision
from app.services.assessment_service import assessment_service

DATASETS_DIR = Path(__file__).resolve().parent.parent.parent / "evaluation" / "datasets"


@pytest.mark.asyncio
async def test_mt_en_hi_golden_accuracy():
    """Verify decision gates on English -> Hindi golden dataset."""
    dataset_file = DATASETS_DIR / "mt_en_hi_golden.json"
    assert dataset_file.exists(), f"Missing dataset: {dataset_file}"

    with open(dataset_file, "r", encoding="utf-8") as f:
        cases = json.load(f)

    for case in cases:
        req = EvaluationRequestSchema(
            source_text=case["source_text"],
            target_text=case["target_text"],
            source_lang=case["source_lang"],
            target_lang=case["target_lang"],
            session_id=f"test_golden_{case['id']}",
        )
        resp = await assessment_service.evaluate_single(req, reference=case.get("reference_text"))
        expected_decision = case["expected_decision"]

        if expected_decision == "ACCEPT":
            assert resp.decision in (QualityDecision.ACCEPT, QualityDecision.ACCEPT_WITH_WARNINGS), (
                f"Failed case {case['id']} ({case['scenario']}): expected ACCEPT/WARNINGS, got {resp.decision}"
            )
            assert resp.has_critical_error is False
        elif expected_decision == "RETRY_WITH_ALTERNATE_PROVIDER":
            assert resp.decision in (QualityDecision.RETRY_WITH_ALTERNATE_PROVIDER, QualityDecision.REJECT), (
                f"Failed case {case['id']} ({case['scenario']}): expected RETRY/REJECT, got {resp.decision}"
            )
            assert resp.has_critical_error is True


@pytest.mark.asyncio
async def test_mt_hi_en_golden_accuracy():
    """Verify decision gates on Hindi -> English golden dataset."""
    dataset_file = DATASETS_DIR / "mt_hi_en_golden.json"
    assert dataset_file.exists(), f"Missing dataset: {dataset_file}"

    with open(dataset_file, "r", encoding="utf-8") as f:
        cases = json.load(f)

    for case in cases:
        req = EvaluationRequestSchema(
            source_text=case["source_text"],
            target_text=case["target_text"],
            source_lang=case["source_lang"],
            target_lang=case["target_lang"],
            session_id=f"test_golden_{case['id']}",
        )
        resp = await assessment_service.evaluate_single(req, reference=case.get("reference_text"))
        expected_decision = case["expected_decision"]

        if expected_decision == "ACCEPT":
            assert resp.decision in (QualityDecision.ACCEPT, QualityDecision.ACCEPT_WITH_WARNINGS), (
                f"Failed case {case['id']} ({case['scenario']}): expected ACCEPT/WARNINGS, got {resp.decision}"
            )
        elif expected_decision == "RETRY_WITH_ALTERNATE_PROVIDER":
            assert resp.decision in (QualityDecision.RETRY_WITH_ALTERNATE_PROVIDER, QualityDecision.REJECT), (
                f"Failed case {case['id']} ({case['scenario']}): expected RETRY/REJECT, got {resp.decision}"
            )
            assert resp.has_critical_error is True

