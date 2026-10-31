"""Unit tests for fastText Language Detection Provider."""
import pytest
from app.providers.fasttext.provider import FastTextProvider


def test_fasttext_english_detection():
    provider = FastTextProvider()
    assert provider.healthy()
    res = provider.detect("This is a clean English sentence about artificial intelligence.")
    assert res.language == "en"
    assert res.confidence >= 0.80
    assert res.provider == "fasttext"


def test_fasttext_hindi_detection():
    provider = FastTextProvider()
    res = provider.detect("नमस्ते दोस्तों, आज हम एआई के बारे में चर्चा करेंगे।")
    assert res.language == "hi"
    assert res.confidence >= 0.80


def test_fasttext_empty_text():
    provider = FastTextProvider()
    res = provider.detect("   ")
    assert res.language == "und"
    assert res.confidence == 0.0

