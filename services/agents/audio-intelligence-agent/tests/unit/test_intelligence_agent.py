"""Unit tests for OpenAI Agents SDK Acoustic Intelligence Agent."""
import pytest
from app.audio.quality import AudioQualityAnalyzer
from app.models.schemas import AudioChunk, AudioQualityMetrics
from app.services.intelligence_agent import (
    AcousticIntelligenceAgent,
    assess_acoustic_environment_fn,
    flag_segment_for_review_fn,
    recommend_tuning_action_fn,
)


def test_acoustic_tools_direct_execution():
    # Test assess_acoustic_environment tool function
    report = assess_acoustic_environment_fn(snr_db=5.0, clipping_ratio=0.03, noise_level_db=-22.0, speech_duration_ms=500)
    assert "clipping" in report.lower()
    assert "snr" in report.lower()

    # Test recommend_tuning_action tool function
    rec = recommend_tuning_action_fn(current_status="poor", issues_summary="clipping, low snr")
    assert "gain" in rec.lower() or "attenuation" in rec.lower()

    # Test flag_segment_for_review tool function
    flag = flag_segment_for_review_fn(segment_id="seg_123", reason="Severe distortion")
    assert "seg_123" in flag


@pytest.mark.asyncio
async def test_intelligence_agent_fast_path():
    agent = AcousticIntelligenceAgent()
    q_good = AudioQualityMetrics(
        rms=0.1,
        peak=0.5,
        snr_db=25.0,
        clipping_ratio=0.0,
        silence_ratio=0.1,
        speech_duration_ms=1000,
        noise_level_db=-50.0,
        confidence=0.95,
        quality_status="good",
        issues=[],
    )
    chunk = AudioChunk(
        session_id="s1",
        conversation_id="c1",
        speaker_id="u1",
        segment_id="seg_clean",
        sequence=1,
        start_ms=0,
        end_ms=1000,
        duration_ms=1000,
        quality=q_good,
        status="final",
    )
    diag = await agent.analyze_segment(chunk)
    assert diag["acoustic_status"] == "optimal"
    assert diag["flagged_for_review"] is False


@pytest.mark.asyncio
async def test_intelligence_agent_degraded_acoustic_diagnosis():
    agent = AcousticIntelligenceAgent()
    q_poor = AudioQualityMetrics(
        rms=0.02,
        peak=0.99,
        snr_db=4.0,
        clipping_ratio=0.08,
        silence_ratio=0.2,
        speech_duration_ms=800,
        noise_level_db=-18.0,
        confidence=0.25,
        quality_status="poor",
        issues=["clipping_detected: 8.0%", "low_snr: 4.0dB"],
    )
    chunk = AudioChunk(
        session_id="s1",
        conversation_id="c1",
        speaker_id="u1",
        segment_id="seg_distorted",
        sequence=2,
        start_ms=1000,
        end_ms=1800,
        duration_ms=800,
        quality=q_poor,
        status="final",
    )
    diag = await agent.analyze_segment(chunk)
    assert diag["acoustic_status"] == "poor"
    assert diag["flagged_for_review"] is True
    assert "clipping" in diag["diagnosis"].lower() or "attenuation" in diag["diagnosis"].lower()
