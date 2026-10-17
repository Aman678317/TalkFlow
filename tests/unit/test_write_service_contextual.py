import pytest
from app.services.write_service import improve_text, improve_text_async, _protect_immutable_spans, _restore_immutable_spans


def test_immutable_spans_protects_urls_emails_numbers_and_code():
    text = "Visit https://globaltalk.example.com or email ops@talkflow.ai with 42 items, $1,500.50 budget and `const x = 10;`."
    masked, protected = _protect_immutable_spans(text)

    assert "https://globaltalk.example.com" not in masked
    assert "ops@talkflow.ai" not in masked
    assert "$1,500.50" not in masked
    assert "`const x = 10;`" not in masked
    assert "__TF_IMMUTABLE_" in masked

    restored = _restore_immutable_spans(masked, protected)
    assert restored == text


def test_write_service_generates_granular_diffs():
    text = "hlo world, this is a exampel with bad writen words."
    res = improve_text(text, language="en", style="business", tone="professional")

    assert res.improved_text != text
    assert len(res.diffs) > 0
    # Check that diffs have original, replacement, diff_type, explanation
    for diff in res.diffs:
        assert diff.original
        assert diff.replacement
        assert diff.diff_type in ("spelling", "grammar", "punctuation", "style", "phrasing")
        assert diff.explanation


@pytest.mark.asyncio
async def test_improve_text_async_backward_compatibility():
    res = await improve_text_async(
        "Aman wrote an exampel with teh correct numbers 42 and https://example.com.",
        language="en",
        corrections_only=True,
    )
    assert "exampel" not in res.improved_text
    assert "example" in res.improved_text
    assert "42" in res.improved_text
    assert "https://example.com" in res.improved_text
