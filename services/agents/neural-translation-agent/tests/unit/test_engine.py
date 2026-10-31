"""Unit tests for TranslationEngine, SpanProtector, and GlossaryManager."""
import pytest
from app.models.schemas import TranslationRequestSchema, BatchTranslationRequestSchema
from app.quality.protected_spans import SpanProtector
from app.glossary.glossary_manager import glossary_manager
from app.memory.translation_memory import translation_memory_service, TMEntry
from app.translation.engine import translation_engine
from app.services.fanout_adapter import fanout_coordinator


@pytest.mark.asyncio
async def test_same_language_identity():
    """Verify that source_lang == target_lang returns exact source text with source_equals_target flag."""
    req = TranslationRequestSchema(
        text="नमस्ते दोस्तों",
        source_lang="hi",
        target_lang="hi",
    )
    res = await translation_engine.translate_single(req)
    assert res.text == "नमस्ते दोस्तों"
    assert res.source_equals_target is True
    assert "source_equals_target" in res.quality_flags
    assert res.provider == "identity"


@pytest.mark.asyncio
async def test_span_protection_urls_numbers():
    """Verify URLs and numbers are wrapped and restored without corruption."""
    sp = SpanProtector()
    src = "Deploy to https://talkflow.ai/v1 or call 9876543210."
    prot = sp.protect(src)
    assert "https://talkflow.ai/v1" not in prot
    assert "9876543210" not in prot

    restored = sp.restore(prot)
    assert "https://talkflow.ai/v1" in restored
    assert "9876543210" in restored


@pytest.mark.asyncio
async def test_glossary_enforcement():
    """Verify source terms are substituted by preferred target terms."""
    glossary = {"artificial intelligence": "कृत्रिम बुद्धिमत्ता", "cloud": "क्लाउड"}
    text = "We love artificial intelligence in the cloud."
    protected, mapping = glossary_manager.protect_glossary_terms(text, glossary)
    assert len(mapping) == 2

    # Simulate translation where model preserved placeholder
    restored = glossary_manager.restore_glossary_terms(protected, mapping)
    assert "कृत्रिम बुद्धिमत्ता" in restored
    assert "क्लाउड" in restored


@pytest.mark.asyncio
async def test_translation_memory_exact_match():
    """Verify that approved TM entry returns immediately without calling MT model."""
    entry = TMEntry(
        entry_id="e1",
        tm_id="tm_test",
        org_id="tenant_123",
        source_text="Welcome to TalkFlow.",
        target_text="TalkFlow मध्ये आपले स्वागत आहे.",
        source_lang="en",
        target_lang="mr",
        approved=True,
    )
    translation_memory_service.add_entry(entry)

    req = TranslationRequestSchema(
        text="Welcome to TalkFlow.",
        source_lang="en",
        target_lang="mr",
        session_id="tenant_123",
        tm_id="tm_test",
    )
    res = await translation_engine.translate_single(req)
    assert res.text == "TalkFlow मध्ये आपले स्वागत आहे."
    assert res.tm_match == "exact"
    assert res.provider == "translation_memory"


@pytest.mark.asyncio
async def test_multi_target_fanout_deduplication():
    """Verify that multiple identical target requests are deduplicated into 1 job."""
    batch_req = BatchTranslationRequestSchema(
        text="नमस्ते दोस्तों",
        source_lang="hi",
        target_langs=["en", "mr", "en", "en", "ja"],
    )
    res = await fanout_coordinator.execute_fanout(batch_req)
    assert res.requested_targets_count == 5
    assert res.unique_translation_jobs_count == 3  # en, mr, ja
    assert "en" in res.results
    assert "mr" in res.results
    assert "ja" in res.results

