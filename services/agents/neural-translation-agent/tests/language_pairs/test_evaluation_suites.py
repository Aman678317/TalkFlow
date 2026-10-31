"""Evaluation test suites verifying Indian language pairs and code-switching."""
import pytest
from app.models.schemas import TranslationRequestSchema
from app.translation.engine import translation_engine


@pytest.mark.asyncio
async def test_pair_hi_to_en():
    req = TranslationRequestSchema(
        text="नमस्ते दोस्तों, आज हम AI के बारे में बात करेंगे।",
        source_lang="hi",
        target_lang="en",
    )
    res = await translation_engine.translate_single(req)
    assert len(res.text) > 5
    assert res.target_lang == "en"


@pytest.mark.asyncio
async def test_pair_hi_to_mr():
    req = TranslationRequestSchema(
        text="नमस्ते दोस्तों, आज हम AI के बारे में बात करेंगे।",
        source_lang="hi",
        target_lang="mr",
    )
    res = await translation_engine.translate_single(req)
    assert len(res.text) > 5
    assert res.target_lang == "mr"


@pytest.mark.asyncio
async def test_pair_en_to_hi():
    req = TranslationRequestSchema(
        text="Hello friends, today we will talk about AI.",
        source_lang="en",
        target_lang="hi",
    )
    res = await translation_engine.translate_single(req)
    assert len(res.text) > 5
    assert res.target_lang == "hi"


@pytest.mark.asyncio
async def test_pair_en_to_mr():
    req = TranslationRequestSchema(
        text="Hello friends, today we will talk about AI.",
        source_lang="en",
        target_lang="mr",
    )
    res = await translation_engine.translate_single(req)
    assert len(res.text) > 5
    assert res.target_lang == "mr"


@pytest.mark.asyncio
async def test_hinglish_code_switching():
    req = TranslationRequestSchema(
        text="Hello everyone, aaj hum new AI project discuss karenge.",
        source_lang="hi",
        target_lang="en",
    )
    res = await translation_engine.translate_single(req)
    assert len(res.text) > 10
    # Technical words like AI, project should survive
    assert "AI" in res.text or "ai" in res.text.lower()

