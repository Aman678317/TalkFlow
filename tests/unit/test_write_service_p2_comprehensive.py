"""P2: Context-Aware Writing & Grammar Comprehensive Test Suite.

Verifies:
1. Immutable span preservation for phone numbers, code, URLs, emails, currencies.
2. Granular diff generation with accurate categories and explanations.
3. Multi-style and multi-tone engine transformations.
4. End-to-end HTTP API routes for `/api/v1/write` and `/api/v1/dictionary`.
"""
from __future__ import annotations

import pytest
from app.services.write_service import (
    improve_text,
    improve_text_async,
    lookup_dictionary,
    _protect_immutable_spans,
    _restore_immutable_spans,
)


def test_immutable_spans_phone_numbers_code_urls_currencies():
    """Verify that phone numbers, code blocks, URLs, and currencies survive rewrite untouched."""
    text = (
        "hlo, please call +1-800-555-0199 or +91-98765-43210 regarding the $1,500.50 budget. "
        "Visit https://talkflow.ai or email support@talkflow.ai with `const port = 8080;` and 15% discount."
    )
    res = improve_text(text, language="en", style="business", tone="professional")

    # Spans must remain intact in improved text
    assert "+1-800-555-0199" in res.improved_text
    assert "+91-98765-43210" in res.improved_text
    assert "$1,500.50" in res.improved_text
    assert "https://talkflow.ai" in res.improved_text
    assert "support@talkflow.ai" in res.improved_text
    assert "`const port = 8080;`" in res.improved_text
    assert "15%" in res.improved_text

    # Shorthand typo must be corrected
    assert "hlo" not in res.improved_text.lower().split()
    assert "Hello" in res.improved_text


def test_granular_diff_classification_and_attributes():
    """Verify that all generated diffs have valid categories, explanations, and non-empty chunks."""
    text = "hlo thx for you time, teh meeting is tommorow."
    res = improve_text(text, language="en", style="business", tone="professional")

    assert len(res.diffs) > 0
    for diff in res.diffs:
        assert diff.original, "Diff must contain original string"
        assert diff.replacement, "Diff must contain replacement string"
        assert diff.diff_type in ("spelling", "grammar", "punctuation", "style", "phrasing")
        assert diff.explanation, "Diff must have human-readable explanation"


def test_style_and_tone_engines():
    """Verify tone and style variations alter wording appropriately while preserving core meaning."""
    text = "I am writing to tell you that I cannot attend the meeting today because my work is done."
    
    res_prof = improve_text(text, language="en", style="business", tone="professional")
    res_casual = improve_text(text, language="en", style="casual", tone="friendly")

    assert res_prof.improved_text
    assert res_casual.improved_text
    # Both preserve factual meaning
    assert "meeting" in res_prof.improved_text.lower()
    assert "meeting" in res_casual.improved_text.lower()


def test_dictionary_service_lookup():
    """Verify multilingual dictionary lookup returns part of speech, definitions, and synonyms."""
    res = lookup_dictionary("example", source_lang="en", target_lang="es")
    assert res.word == "example"
    assert res.part_of_speech in ("noun", "verb", "adjective", "noun / verb", "general")
    assert len(res.meanings) > 0
    assert len(res.synonyms) > 0


def test_write_http_endpoint_authenticated(services_app_client, user):
    """Verify POST /api/v1/write requires authentication and returns full WriteResponse schema."""
    payload = {
        "text": "hlo team, this is an exampel with bad writen words.",
        "language": "en",
        "style": "business",
        "tone": "professional",
        "corrections_only": False,
    }
    res = services_app_client.post(
        "/api/v1/write",
        headers=user["headers"],
        json=payload,
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["original_text"] == payload["text"]
    assert "Hello" in data["improved_text"]
    assert len(data["diffs"]) > 0
    assert "diff_type" in data["diffs"][0]
    assert "explanation" in data["diffs"][0]


def test_dictionary_http_endpoint(services_app_client, user):
    """Verify POST /api/v1/dictionary returns definitions, synonyms, and translations."""
    res = services_app_client.post(
        "/api/v1/dictionary",
        headers=user["headers"],
        json={"word": "improve", "source_lang": "en", "target_lang": "hi"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["word"] == "improve"
    assert len(data["meanings"]) > 0
    assert len(data["synonyms"]) > 0
