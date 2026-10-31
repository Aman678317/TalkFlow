"""Unit tests for ConfidenceEvaluator and anti-hallucination filter."""
from app.models.schemas import STTResult
from app.stt.confidence import ConfidenceEvaluator


def test_clean_speech_passes():
    evaluator = ConfidenceEvaluator()
    res = STTResult(
        text="Hello everyone welcome to the meeting",
        language="en",
        language_probability=0.98,
        confidence=0.95,
        no_speech_prob=0.01,
        avg_logprob=-0.12,
    )
    cleaned, flags = evaluator.evaluate(res)
    assert cleaned == "Hello everyone welcome to the meeting"
    assert len(flags) == 0


def test_high_no_speech_prob_suppressed():
    evaluator = ConfidenceEvaluator(no_speech_threshold=0.60, suppress_silence_loops=True)
    res = STTResult(
        text="random hallucination from silence",
        language="en",
        language_probability=0.20,
        confidence=0.10,
        no_speech_prob=0.85,
        avg_logprob=-2.4,
    )
    cleaned, flags = evaluator.evaluate(res)
    assert cleaned == ""
    assert "high_no_speech_prob" in flags


def test_known_whisper_hallucination_dropped_on_low_confidence():
    evaluator = ConfidenceEvaluator()
    res = STTResult(
        text="Thank you for watching.",
        language="en",
        language_probability=0.5,
        confidence=0.3,
        no_speech_prob=0.45,
    )
    cleaned, flags = evaluator.evaluate(res)
    assert cleaned == ""
    assert "known_hallucination_pattern" in flags


def test_consecutive_repetition_loop_collapsed():
    evaluator = ConfidenceEvaluator(max_repetition_count=3)
    res = STTResult(
        text="yes yes yes yes yes yes we agree",
        language="en",
        confidence=0.8,
        no_speech_prob=0.05,
    )
    cleaned, flags = evaluator.evaluate(res)
    assert "repetition_loop_detected" in flags
    # Excessive consecutive repetitions collapsed
    assert cleaned == "yes yes we agree"

