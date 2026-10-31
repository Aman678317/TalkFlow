"""Unit tests for acoustic quality analysis, clipping, SNR, and diagnostics."""
from app.audio.quality import AudioQualityAnalyzer
from tests.fixtures.audio_fixtures import (
    generate_clipped_signal,
    generate_noisy_speech,
    generate_silence,
    generate_speech_like_signal,
)


def test_silence_quality_detection():
    analyzer = AudioQualityAnalyzer()
    silence_pcm = generate_silence(duration_ms=500, sample_rate=16000)
    q = analyzer.analyze(silence_pcm, speech_duration_ms=0, sample_rate=16000)

    assert q.rms < 0.001
    assert q.peak < 0.001
    assert q.silence_ratio > 0.90
    assert q.clipping_ratio == 0.0


def test_clean_speech_quality():
    analyzer = AudioQualityAnalyzer()
    speech_pcm = generate_speech_like_signal(duration_ms=1000, sample_rate=16000, amplitude=0.6)
    q = analyzer.analyze(speech_pcm, speech_duration_ms=1000, sample_rate=16000)

    assert q.rms > 0.05
    assert q.peak > 0.3
    assert q.snr_db > 12.0
    assert q.clipping_ratio < 0.005
    assert q.quality_status in ("good", "fair")


def test_clipping_detection():
    analyzer = AudioQualityAnalyzer(clipping_warning_ratio=0.01)
    clipped_pcm = generate_clipped_signal(duration_ms=500, sample_rate=16000, amplitude=2.5)
    q = analyzer.analyze(clipped_pcm, speech_duration_ms=500, sample_rate=16000)

    assert q.clipping_ratio > 0.05
    assert any("clipping_detected" in issue for issue in q.issues)
    assert q.quality_status == "poor"


def test_low_snr_background_noise():
    analyzer = AudioQualityAnalyzer(snr_warning_threshold_db=10.0)
    # Signal mixed with loud noise (SNR = 2 dB)
    noisy_pcm = generate_noisy_speech(duration_ms=1000, sample_rate=16000, snr_db=2.0)
    q = analyzer.analyze(noisy_pcm, speech_duration_ms=800, sample_rate=16000)

    assert q.snr_db < 10.0
    assert any("low_snr" in issue for issue in q.issues)


def test_quiet_speech_volume():
    analyzer = AudioQualityAnalyzer()
    quiet_pcm = generate_speech_like_signal(duration_ms=500, sample_rate=16000, amplitude=0.01)
    q = analyzer.analyze(quiet_pcm, speech_duration_ms=500, sample_rate=16000)

    assert q.rms < 0.01
    assert any("low_volume_speech" in issue for issue in q.issues)

