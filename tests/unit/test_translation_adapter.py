import pytest
from gt_ai.translation.translator import IndicTranslator, Translator, TranslationResponse, INDIC_LANGUAGES
from gt_ai.types import TranslationRequest, TranslationResult


class MockTranslationProvider:
    def __init__(self):
        self.last_req: TranslationRequest | None = None

    async def translate(self, req: TranslationRequest) -> TranslationResult:
        self.last_req = req
        # Mock translation output
        if req.target_lang == "hi":
            translated = "नमस्ते, आप कैसे हैं"
        elif req.target_lang == "mr":
            translated = "नमस्कार, तुम्ही कसे आहात"
        elif req.target_lang == "en":
            translated = "Hello, how are you"
        else:
            translated = f"Translated to {req.target_lang}: {req.text}"

        return TranslationResult(
            text=translated,
            source_lang=req.source_lang,
            target_lang=req.target_lang,
            model="mock-nllb",
            provider="mock",
            latency_ms=45.0,
        )


@pytest.mark.asyncio
async def test_indic_translator_indic_languages():
    provider = MockTranslationProvider()
    translator = IndicTranslator(provider)

    assert "hi" in INDIC_LANGUAGES
    assert "mr" in INDIC_LANGUAGES
    assert "ta" in INDIC_LANGUAGES
    assert "bn" in INDIC_LANGUAGES

    # Translate English to Hindi
    res_hi = await translator.translate("Hello, how are you", "en", "hi")
    assert isinstance(res_hi, TranslationResponse)
    assert res_hi.text.endswith("।")  # Devanagari TTS boundary normalized
    assert res_hi.detected_source_language == "en"

    # Translate English to Marathi
    res_mr = await translator.translate("Hello, how are you", "en", "mr")
    assert res_mr.text.endswith("।")

    # Translate Hindi to English
    res_en = await translator.translate("नमस्ते आप कैसे हैं", "hi", "en")
    assert res_en.text.endswith(".")


@pytest.mark.asyncio
async def test_indic_translator_context_capping():
    provider = MockTranslationProvider()
    translator = IndicTranslator(provider)

    # Provide lengthy context (> 300 chars)
    long_context = "This is a very long previous segment. " * 15
    assert len(long_context) > 250

    await translator.translate(
        text="What about the meeting?",
        source_language="en",
        target_language="hi",
        context=long_context,
    )

    assert provider.last_req is not None
    assert len(provider.last_req.context) == 1
    # Check that context was capped to at most 250 characters
    assert len(provider.last_req.context[0]) <= 250


@pytest.mark.asyncio
async def test_indic_translator_same_language_passthrough():
    provider = MockTranslationProvider()
    translator = IndicTranslator(provider)

    res = await translator.translate("Direct message", "en", "en")
    assert res.text == "Direct message"
    assert res.provider == "identity"
