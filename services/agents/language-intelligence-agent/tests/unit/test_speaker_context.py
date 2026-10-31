"""Unit tests for Speaker Language Context and Hysteresis."""
import pytest
from app.sessions.speaker_context import SpeakerLanguageContext


def test_speaker_hysteresis_loanword_suppression():
    ctx = SpeakerLanguageContext(speaker_id="user_spk_01", window_size=5, switch_threshold_count=2)

    # 1. Speaker starts in Hindi
    dominant = ctx.record_utterance("utt_1", "hi", 0.95)
    assert dominant == "hi"

    # 2. Speaker says an isolated English loanword (e.g. "Okay")
    dominant = ctx.record_utterance("utt_2", "en", 0.80)
    # Hysteresis should NOT flip-flop to English on a single loanword!
    assert dominant == "hi", "Should suppress isolated English loanword"

    # 3. Speaker continues in Hindi
    dominant = ctx.record_utterance("utt_3", "hi", 0.90)
    assert dominant == "hi"


def test_speaker_hysteresis_genuine_language_switch():
    ctx = SpeakerLanguageContext(speaker_id="user_spk_02", window_size=5, switch_threshold_count=2)

    # Starts in Hindi
    ctx.record_utterance("utt_1", "hi", 0.90)
    assert ctx.dominant_language == "hi"

    # Speaks 2 consecutive high-confidence English utterances
    ctx.record_utterance("utt_2", "en", 0.85)
    ctx.record_utterance("utt_3", "en", 0.88)

    # Now hysteresis should confirm genuine switch to English
    assert ctx.dominant_language == "en"

