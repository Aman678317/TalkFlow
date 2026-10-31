"""Unit tests for LanguageRegistry and Indian language support."""
from app.stt.language_hints import LanguageRegistry


def test_registry_contains_indic_languages():
    indic_codes = ["hi", "mr", "bn", "ta", "te", "gu", "kn", "ml", "pa", "ur"]
    for code in indic_codes:
        cap = LanguageRegistry.get_capability(code)
        assert cap is not None, f"Language {code} missing from registry"
        assert cap.available is True
        assert cap.code_switch_supported is True


def test_registry_extract_language_hint():
    hint, prob = LanguageRegistry.extract_language_hint("hi-IN", 0.94)
    assert hint == "hi"
    assert prob == 0.94

    # Unknown language falls back safely
    hint_fallback, _ = LanguageRegistry.extract_language_hint("unknown_lang", 0.1)
    assert hint_fallback == "en"

