import pytest
from app.config import settings
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


# --------------------------------------------------------------------------- #
# Tier 2 — provider-backed neural grammar (used when LLM_HTTP_URL is set)
# --------------------------------------------------------------------------- #

@pytest.fixture
def neural_url(monkeypatch):
    monkeypatch.setattr(settings, "llm_http_url", "http://llm.local")
    monkeypatch.setattr(settings, "llm_model", "test-llm")
    return settings


async def _stub_chat(monkeypatch, reply: str, calls: list[str] | None = None):
    """Intercept the OpenAI-compatible endpoint write_service talks to."""
    from gt_ai.summarize import llm_http as llm_mod

    class FakeChat:
        async def _chat(self, system: str, user: str) -> str:
            if calls is not None:
                calls.append(user)
            return reply

    monkeypatch.setattr(llm_mod, "LlmHttpSummarizer", lambda **kw: FakeChat())


@pytest.mark.asyncio
async def test_neural_tier_applies_contextual_rewrite_when_provider_succeeds(
        neural_url, monkeypatch):
    calls: list[str] = []
    await _stub_chat(monkeypatch, "Hello team, I will send the report tomorrow. "
                                   "It is ready except for missing figures.",
                     calls)
    res = await improve_text_async(
        "Hlo team, i will sending the report tmrw. its ready accept missing figers.")
    assert res.improved_text.startswith("Hello team")
    assert res.changes_count > 0
    # protected span instruction reached the provider
    assert calls and isinstance(calls[0], str)


@pytest.mark.asyncio
async def test_neural_tier_rejected_when_protected_spans_are_mangled(
        neural_url, monkeypatch):
    await _stub_chat(
        monkeypatch,
        # provider dropped the protected number token: unacceptable
        "Hlo team, see https://replaced.example and call me.")
    res = await improve_text_async(
        "Hlo team, see https://real-docs.example.com/doc and call 555 the office.")
    # fell back to the offline rule engine; URL survived verbatim
    assert "https://real-docs.example.com/doc" in res.improved_text
    assert "replaced.example" not in res.improved_text


@pytest.mark.asyncio
async def test_neural_tier_falls_back_to_rules_on_provider_outage(
        neural_url, monkeypatch):
    from gt_ai.summarize import llm_http as llm_mod

    class Down:
        async def _chat(self, system: str, user: str) -> str:
            raise RuntimeError("connection refused")

    monkeypatch.setattr(llm_mod, "LlmHttpSummarizer", lambda **kw: Down())
    res = await improve_text_async(
        "Aman wrote an exampel with teh numbers 42 and https://example.com.")
    assert "exampel" not in res.improved_text
    assert "42" in res.improved_text
    assert "https://example.com" in res.improved_text


@pytest.mark.asyncio
async def test_neural_tier_disabled_without_llm_url(monkeypatch):
    monkeypatch.setattr(settings, "llm_http_url", "")
    res = await improve_text_async("hlo world, this is a exampel.")
    assert res is not None
    assert res.improved_text != "hlo world, this is a exampel."
