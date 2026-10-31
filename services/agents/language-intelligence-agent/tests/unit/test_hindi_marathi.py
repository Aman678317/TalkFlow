"""Unit tests for Devanagari Hindi vs. Marathi lexical disambiguation."""
import pytest
from app.language.registry import LanguageProfileRegistry


def test_marathi_disambiguation():
    # Marathi text containing 'आहे', 'तुम्ही', 'कसे'
    mr_text = "नमस्कार, तुम्ही कसे आहात? हे काम खूप छान आहे."
    lang, conf = LanguageProfileRegistry.disambiguate_devanagari(mr_text)
    assert lang == "mr"
    assert conf >= 0.85


def test_hindi_disambiguation():
    # Hindi text containing 'है', 'आप', 'कैसे', 'बहुत'
    hi_text = "नमस्ते, आप कैसे हैं? यह काम बहुत अच्छा है।"
    lang, conf = LanguageProfileRegistry.disambiguate_devanagari(hi_text)
    assert lang == "hi"
    assert conf >= 0.85


def test_neutral_devanagari_defaults_to_hindi():
    neutral_text = "राम और श्याम"
    lang, conf = LanguageProfileRegistry.disambiguate_devanagari(neutral_text)
    assert lang == "hi"

