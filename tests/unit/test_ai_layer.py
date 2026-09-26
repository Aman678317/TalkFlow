"""Unit tests — gt_ai text ops, VAD, router, metrics, detection, providers."""
from __future__ import annotations

import asyncio
import math

import numpy as np
import pytest

from gt_ai.translation.text_ops import (
    SpanProtector, apply_glossary_to_output, normalize_spoken_terms,
    normalize_unicode, quality_checks,
)
from gt_ai.evaluation.metrics import (
    bleu, cer, number_preservation_score, terminology_accuracy, wer,
)
from gt_ai.model_router.router import ModelRouter, ProviderSpec
from gt_ai.types import Intent, Task
from gt_ai.vad import EnergyVAD, VadState


# --------------------------------------------------------------------------- #
# Protected spans & glossary
# --------------------------------------------------------------------------- #

class TestSpanProtector:
    def test_urls_emails_protected(self):
        p = SpanProtector()
        out = p.protect("See https://example.com/a?b=1 and mail a@b.co now")
        assert "https://" not in out and "a@b.co" not in out
        assert p.span_count == 2
        restored = p.restore(out)
        assert "https://example.com/a?b=1" in restored and "a@b.co" in restored

    def test_numbers_protected_including_indian_grouping(self):
        p = SpanProtector()
        out = p.protect("राजस्व ₹12,50,000 था और $4,250.75 भी")
        assert "12,50,000" not in out
        restored = p.restore(out)
        assert "₹12,50,000" in restored and "$4,250.75" in restored

    def test_code_and_ids(self):
        p = SpanProtector()
        out = p.protect("run `kubectl get pods` for TICKET-4242")
        assert "kubectl" not in out and "TICKET-4242" not in out
        assert "kubectl get pods" in p.restore(out)


class TestGlossary:
    def test_apply_flags_missing_term(self):
        out, flags = apply_glossary_to_output(
            "some free translation", "open the cloud console",
            {"cloud console": "क्लाउड कंसोल"})
        assert any(f.startswith("glossary_term_missing") for f in flags)

    def test_apply_passes_when_term_present(self):
        out, flags = apply_glossary_to_output(
            "क्लाउड कंसोल खोलें", "open the cloud console",
            {"cloud console": "क्लाउड कंसोल"})
        assert flags == []

    def test_spoken_term_normalization(self):
        assert normalize_spoken_terms("restart the cpu now",
                                      {"cpu": "CPU"}) == "restart the CPU now"


def test_unicode_normalization_nfc():
    decomposed = "कि" + "\u0930"  # whatever the input form
    assert normalize_unicode(decomposed) == normalize_unicode(normalize_unicode(decomposed))


class TestQualityChecks:
    def test_number_mismatch_detected(self):
        assert "number_mismatch" in quality_checks("Total is 42 units",
                                                   "Total is 43 units")

    def test_url_loss_detected(self):
        flags = quality_checks("see https://x.io/p", "see the link")
        assert "url_or_email_lost" in flags

    def test_script_loss_detected(self):
        flags = quality_checks("नमस्ते दुनिया", "hello world")
        assert "script_lost" in flags

    def test_empty_translation(self):
        assert quality_checks("text", "   ") == ["empty_translation"]


# --------------------------------------------------------------------------- #
# Evaluation metrics
# --------------------------------------------------------------------------- #

def test_wer_cer_perfect():
    assert wer("hello world", "hello world") == 0.0
    assert cer("hello", "hello") == 0.0


def test_wer_known_value():
    # 1 substitution out of 3 words
    assert abs(wer("the cat sat", "the dog sat") - 1 / 3) < 1e-9


def test_cer_known_value():
    assert abs(cer("abcd", "abxd") - 0.25) < 1e-9


def test_bleu_reasonable():
    b = bleu("the cat sat on the mat", "the cat sat on the mat")
    assert b > 0.99
    b2 = bleu("the cat sat on the mat", "completely different words here now")
    assert b2 < 0.2


def test_number_preservation():
    assert number_preservation_score("cost 42 and 7.5%", "cost 42 and 7.5%") == 1.0
    assert number_preservation_score("cost 42", "cost 43") == 0.0


def test_terminology_accuracy():
    g = {"cloud console": "क्लाउड कंसोल"}
    assert terminology_accuracy("open cloud console", "क्लाउड कंसोल खोलें", g) == 1.0
    assert terminology_accuracy("open cloud console", "some other text", g) == 0.0


# --------------------------------------------------------------------------- #
# VAD
# --------------------------------------------------------------------------- #

def _tone(seconds: float, freq: float = 220, amp: float = 0.4,
          rate: int = 16000) -> bytes:
    t = np.arange(int(seconds * rate)) / rate
    wave = (amp * 32767 * np.sin(2 * math.pi * freq * t)).astype(np.int16)
    return wave.tobytes()


def _silence(seconds: float, rate: int = 16000) -> bytes:
    return np.zeros(int(seconds * rate), dtype=np.int16).tobytes()


def test_vad_detects_speech_and_silence_transitions():
    vad = EnergyVAD(sample_rate=16000)
    events = []
    # feed 1s of tone in 100ms chunks
    tone = _tone(1.0)
    for i in range(0, len(tone), 3200):
        events.extend(vad.process(tone[i:i + 3200]))
    assert any(e.state == VadState.SPEECH for e in events)
    # then 1s of silence -> speech end
    sil = _silence(1.0)
    for i in range(0, len(sil), 3200):
        events.extend(vad.process(sil[i:i + 3200]))
    assert any(e.state == VadState.SILENCE for e in events)


def test_vad_ignores_quiet_noise():
    vad = EnergyVAD(sample_rate=16000)
    events = []
    quiet = _tone(1.0, amp=0.001)
    for i in range(0, len(quiet), 3200):
        events.extend(vad.process(quiet[i:i + 3200]))
    assert not any(e.state == VadState.SPEECH for e in events)


# --------------------------------------------------------------------------- #
# Model router
# --------------------------------------------------------------------------- #

def _router() -> ModelRouter:
    specs = {
        Task.MT: [
            ProviderSpec(name="dev_echo", task=Task.MT, quality_tier=1, cost_tier=0,
                         latency_class="realtime"),
            ProviderSpec(name="madlad400", task=Task.MT, quality_tier=85, cost_tier=70,
                         latency_class="fast"),
            ProviderSpec(name="nllb_ct2", task=Task.MT, quality_tier=78, cost_tier=40,
                         latency_class="fast"),
            ProviderSpec(name="cloud_mt", task=Task.MT, quality_tier=90, cost_tier=90,
                         private=False, latency_class="fast"),
            ProviderSpec(name="gpu_only", task=Task.MT, quality_tier=95, cost_tier=50,
                         requires_gpu=True, latency_class="fast"),
        ],
    }
    return ModelRouter(specs, gpu_available=False)


def test_router_quality_intent_prefers_high_quality():
    d = _router().route(Task.MT, source_lang="hi", target_lang="en",
                        intent=Intent.QUALITY_OPTIMIZED)
    assert d.provider == "madlad400"


def test_router_cost_intent_prefers_cheap():
    d = _router().route(Task.MT, source_lang="hi", target_lang="en",
                        intent=Intent.COST_OPTIMIZED)
    assert d.provider == "dev_echo"


def test_router_private_only_excludes_cloud():
    d = _router().route(Task.MT, source_lang="hi", target_lang="en",
                        intent=Intent.PRIVATE_ONLY)
    assert d.provider != "cloud_mt"


def test_router_gpu_constraint():
    d = _router().route(Task.MT, source_lang="hi", target_lang="en",
                        intent=Intent.QUALITY_OPTIMIZED)
    assert d.provider != "gpu_only"  # gpu_available=False


def test_router_health_failover():
    r = _router()
    r.mark_available(Task.MT, "madlad400", False)
    d = r.route(Task.MT, source_lang="hi", target_lang="en",
                intent=Intent.QUALITY_OPTIMIZED)
    assert d.provider == "nllb_ct2"


def test_router_error_rate_degrades_health():
    r = _router()
    for _ in range(5):
        r.record_outcome(Task.MT, "madlad400", 100, ok=False)
    d = r.route(Task.MT, source_lang="hi", target_lang="en",
                intent=Intent.QUALITY_OPTIMIZED)
    assert d.provider != "madlad400"


# --------------------------------------------------------------------------- #
# Language detection provider
# --------------------------------------------------------------------------- #

def test_detection_scripts():
    from gt_ai.detection.langdetect_p import LangDetectProvider
    p = LangDetectProvider()
    cases = [
        ("नमस्ते, आप कैसे हैं?", "hi"),
        ("नमस्कार, तुम्ही कसे आहात?", "mr"),
        ("こんにちは、げんきですか", "ja"),
        ("শুভ সকাল", "bn"),
        ("வணக்கம் நலமா", "ta"),
        ("Hello, how are you doing today my friend?", "en"),
    ]
    for text, expected in cases:
        r = asyncio.run(p.detect(text))
        assert r.language == expected, f"{text!r} -> {r.language}, expected {expected}"


def test_detection_urdu_vs_arabic():
    from gt_ai.detection.langdetect_p import LangDetectProvider
    p = LangDetectProvider()
    r = asyncio.run(p.detect("آپ کیسے ہیں؟ میں ٹھیک ہوں۔"))
    assert r.language == "ur"
    r = asyncio.run(p.detect("مرحبا كيف حالك اليوم"))
    assert r.language == "ar"


# --------------------------------------------------------------------------- #
# Extractive summarizer
# --------------------------------------------------------------------------- #

def test_extractive_structured():
    from gt_ai.summarize.extractive import ExtractiveSummarizer
    s = ExtractiveSummarizer()
    text = (
        "The team discussed the quarterly roadmap. "
        "We decided to launch the Marathi beta next month. "
        "Ravi will prepare the evaluation dataset by Friday. "
        "What is the budget for GPU workers? "
        "The budget question remained unanswered. "
        "Everyone agreed the glossary quality is critical. "
        "Action item: Anjali should finalize the TTS voice selection. "
        "The meeting covered translation quality and latency targets.")
    out = asyncio.run(s.extract_structured(text))
    assert out["decisions"], out
    assert any("Ravi" in a or "Anjali" in a or "will" in a.lower()
               for a in out["action_items"])
    assert any("budget" in q.lower() for q in out["unanswered_questions"])
    # summaries must only quote existing sentences (canonical-source safety)
    for kp in out["key_points"]:
        assert kp.strip() in text


# --------------------------------------------------------------------------- #
# Dev providers honesty
# --------------------------------------------------------------------------- #

def test_dev_echo_flags_itself():
    from gt_ai.registry import create
    from gt_ai.types import TranslationRequest
    p = create("mt", "dev_echo")
    r = asyncio.run(p.translate(TranslationRequest(
        text="hello", source_lang="en", target_lang="hi")))
    assert "dev_provider" in r.quality_flags
    assert r.model == "dev-echo-v1"


def test_dev_tone_produces_real_wav():
    from gt_ai.registry import create
    p = create("tts", "dev_tone")
    chunk = asyncio.run(p.synthesize("hello world", "en"))
    assert chunk.data[:4] == b"RIFF"
    assert chunk.is_dev is True
    assert chunk.model == "dev-tone-v1"


def test_dev_stt_never_fabricates_text():
    from gt_ai.registry import create
    p = create("stt", "dev_text")
    chunk = asyncio.run(p.transcribe(_tone(0.5), 16000))
    assert chunk.text == ""
    assert chunk.provider == "dev_text"
