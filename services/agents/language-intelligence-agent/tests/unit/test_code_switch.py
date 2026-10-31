"""Unit tests for Code-Switching Tokenizer and Exact Character Offset Alignment."""
import pytest
from app.detection.code_switch import CodeSwitchDetector


def test_hinglish_code_switching_offsets():
    text = "Hello everyone, aaj hum artificial intelligence ke baare mein discuss karenge."
    spans = CodeSwitchDetector.extract_language_spans(text)

    assert len(spans) >= 2, "Should identify at least 2 code-switched language spans"

    # Verify character offsets strictly match original text slices
    for s in spans:
        slice_text = text[s.text_start_offset:s.text_end_offset]
        assert slice_text == s.text, f"Offset slice '{slice_text}' does not match span text '{s.text}'"

    # Verify presence of English and Hindi spans
    langs = {s.language for s in spans}
    assert "en" in langs, "Should contain English span"
    assert "hi" in langs, "Should contain Hindi span"


def test_pure_english_single_span():
    text = "Speech recognition is transforming global communication."
    spans = CodeSwitchDetector.extract_language_spans(text)
    assert len(spans) == 1
    assert spans[0].language == "en"
    assert text[spans[0].text_start_offset:spans[0].text_end_offset] == spans[0].text


def test_mixed_script_code_switch():
    text = "Welcome to our meeting, आज हम चर्चा करेंगे."
    spans = CodeSwitchDetector.extract_language_spans(text)
    assert len(spans) == 2
    assert spans[0].language == "en"
    assert spans[1].language == "hi"
    assert spans[1].script == "Deva"
