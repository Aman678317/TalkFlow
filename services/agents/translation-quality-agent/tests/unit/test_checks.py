"""Unit tests for deterministic integrity checks."""
from __future__ import annotations

import pytest
from app.checks.currency import CurrencyIntegrityCheck
from app.checks.empty import EmptyTranslationCheck
from app.checks.glossary import GlossaryComplianceCheck
from app.checks.language_script import LanguageScriptIntegrityCheck
from app.checks.length_duplication import LengthAndDuplicationCheck
from app.checks.negation import NegationIntegrityCheck
from app.checks.numbers import NumberIntegrityCheck
from app.checks.urls_emails import URLsEmailsIntegrityCheck
from app.models.schemas import EvaluationRequestSchema, IssueSeverity


def test_empty_check():
    chk = EmptyTranslationCheck()
    req = EvaluationRequestSchema(
        source_text="Hello",
        target_text="",
        source_lang="en",
        target_lang="hi",
    )
    res = chk.run(req)
    assert res.status == "failed"
    assert any(i.code == "empty_translation" for i in res.issues)


def test_number_integrity_preservation():
    chk = NumberIntegrityCheck()
    req = EvaluationRequestSchema(
        source_text="कंपनी ने ₹12,50,000 का निवेश किया।",
        target_text="The company invested ₹12,50,000.",
        source_lang="hi",
        target_lang="en",
    )
    res = chk.run(req)
    assert res.status == "passed"
    assert len(res.issues) == 0


def test_number_integrity_corruption_detected():
    chk = NumberIntegrityCheck()
    # Source has 12,50,000 but candidate has 1,25,000 (single digit drop)
    req = EvaluationRequestSchema(
        source_text="कंपनी ने ₹12,50,000 का निवेश किया।",
        target_text="The company invested ₹1,25,000.",
        source_lang="hi",
        target_lang="en",
    )
    res = chk.run(req)
    assert res.status == "failed"
    assert any(i.code == "number_mismatch" and i.severity == IssueSeverity.CRITICAL for i in res.issues)


def test_currency_corruption_detected():
    chk = CurrencyIntegrityCheck()
    req = EvaluationRequestSchema(
        source_text="The cost is ₹500.",
        target_text="The cost is $500.",  # Rupee corrupted to Dollar
        source_lang="en",
        target_lang="en",
    )
    res = chk.run(req)
    assert res.status == "failed"
    assert any(i.code in ("currency_omission", "currency_corruption") for i in res.issues)


def test_negation_reversal_detected():
    chk = NegationIntegrityCheck()
    req = EvaluationRequestSchema(
        source_text="Do not restart the server now.",
        target_text="सर्वर को अभी पुनः आरंभ करें।",  # Omitted "नहीं" / "ना"
        source_lang="en",
        target_lang="hi",
    )
    res = chk.run(req)
    assert res.status == "failed"
    assert any(i.code == "critical_negation_omission" and i.severity == IssueSeverity.CRITICAL for i in res.issues)


def test_url_loss_detected():
    chk = URLsEmailsIntegrityCheck()
    req = EvaluationRequestSchema(
        source_text="Check docs at https://example.com/api",
        target_text="दस्तावेज़ की जाँच करें।",  # URL lost
        source_lang="en",
        target_lang="hi",
    )
    res = chk.run(req)
    assert res.status == "failed"
    assert any(i.code == "url_loss" for i in res.issues)


def test_target_script_mismatch():
    chk = LanguageScriptIntegrityCheck()
    req = EvaluationRequestSchema(
        source_text="आमचा संघ नवीन प्रकल्पावर चर्चा करेल.",
        target_text="Our team will discuss the new project.",  # Target is 'mr' but output is pure Latin
        source_lang="mr",
        target_lang="mr",
    )
    res = chk.run(req)
    assert res.status == "failed"
    assert any(i.code == "target_script_mismatch" for i in res.issues)


def test_glossary_enforcement():
    chk = GlossaryComplianceCheck()
    req = EvaluationRequestSchema(
        source_text="We need to build Artificial Intelligence systems.",
        target_text="हमें स्मार्ट सॉफ्टवेयर सिस्टम बनाने की जरूरत है।",  # Did not use preferred "कृत्रिम बुद्धिमत्ता"
        source_lang="en",
        target_lang="hi",
        glossary={"Artificial Intelligence": "कृत्रिम बुद्धिमत्ता"},
    )
    res = chk.run(req)
    assert any(i.code == "glossary_term_violation" for i in res.issues)


def test_suspicious_length_ratio():
    chk = LengthAndDuplicationCheck()
    req = EvaluationRequestSchema(
        source_text="Hello.",
        target_text="This is an extremely long hallucinated sentence that keeps going on and on for no apparent reason.",
        source_lang="en",
        target_lang="en",
    )
    res = chk.run(req)
    assert any(i.code == "suspiciously_long" for i in res.issues)

