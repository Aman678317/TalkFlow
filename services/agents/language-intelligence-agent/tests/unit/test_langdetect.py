"""Unit tests for LangDetect Provider and Indic script heuristics."""
import pytest
from app.providers.langdetect.provider import LangDetectProvider


def test_langdetect_english():
    provider = LangDetectProvider()
    assert provider.healthy()
    res = provider.detect("The quick brown fox jumps over the lazy dog.")
    assert res.language == "en"
    assert res.confidence >= 0.70


def test_langdetect_bengali_script():
    provider = LangDetectProvider()
    res = provider.detect("আমি বাংলায় কথা বলি।")
    assert res.language == "bn"
    assert res.confidence >= 0.90


def test_langdetect_tamil_script():
    provider = LangDetectProvider()
    res = provider.detect("வணக்கம் உலகம்.")
    assert res.language == "ta"
    assert res.confidence >= 0.90

