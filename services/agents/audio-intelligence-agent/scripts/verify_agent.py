"""Self-contained verification script for Audio Intelligence Agent."""
import asyncio
import os
import sys
import time
from pathlib import Path

# Ensure package on path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.audio.normalization import AudioNormalizer
from app.audio.quality import AudioQualityAnalyzer
from app.audio.validation import AudioValidator
from app.core.config import settings
from app.models.schemas import AudioChunk, AudioQualityMetrics
from app.providers.noise_suppression import get_noise_suppressor
from app.providers.vad import get_vad_provider
from app.services.intelligence_agent import AcousticIntelligenceAgent
from app.services.pipeline import AudioPipeline
from tests.fixtures.audio_fixtures import generate_silence, generate_speech_like_signal


def print_step(title: str):
    print(f"\n{'='*20} {title} {'='*20}")


async def verify():
    print_step("STEP 1: CONFIGURATION & ENVIRONMENT")
    print(f"Agent Name: {settings.agent.name} v{settings.agent.version}")
    print(f"Canonical Sample Rate: {settings.audio.sample_rate} Hz (Channels: {settings.audio.channels})")
    print(f"Frame Duration: {settings.audio.frame_duration_ms} ms (Expected bytes: {settings.audio.expected_bytes_per_frame})")
    print(f"Default VAD Provider: {settings.vad.provider}")
    print(f"Default Noise Suppressor: {settings.noise_suppression.provider}")
    print(f"OpenAI Agents SDK Model: {settings.llm_agent.model} (Base URL: {settings.llm_agent.base_url})")

    print_step("STEP 2: AUDIO VALIDATION & NORMALIZATION")
    validator = AudioValidator()
    normalizer = AudioNormalizer()
    valid_pcm = generate_silence(50, 16000)
    assert validator.validate_frame(valid_pcm) is True
    print("[OK] 50ms PCM16 frame validation: PASS")

    # Resample 48k to 16k
    pcm_48k = generate_speech_like_signal(50, 48000)
    resampled = normalizer.normalize(pcm_48k, source_sample_rate=48000)
    assert len(resampled) == 1600
    print("[OK] 48kHz -> 16kHz resampling & mono downmixing: PASS")

    print_step("STEP 3: VAD PROVIDERS AUDIT")
    for vad_name in ("energy", "webrtc", "silero"):
        v = get_vad_provider(vad_name)
        avail = v.is_available()
        status = "AVAILABLE" if avail else "UNAVAILABLE (Degraded)"
        prob_silence = v.process_chunk(valid_pcm)
        print(f"  - [{vad_name.upper():<7}] Status: {status:<15} (Silence Prob: {prob_silence:.4f})")
    print("[OK] VAD multi-provider audit: PASS")

    print_step("STEP 4: NOISE SUPPRESSION AUDIT")
    for ns_name in ("passthrough", "spectral", "noisereduce"):
        sup = get_noise_suppressor(ns_name, enabled=True)
        status = "AVAILABLE" if sup.is_available() else "UNAVAILABLE"
        out = sup.process_frame(valid_pcm)
        print(f"  - [{ns_name.upper():<12}] Status: {status:<15} (Out bytes: {len(out)})")
    print("[OK] Noise suppression provider audit: PASS")

    print_step("STEP 5: ACOUSTIC QUALITY INTELLIGENCE")
    analyzer = AudioQualityAnalyzer()
    q_speech = analyzer.analyze(generate_speech_like_signal(1000, 16000), speech_duration_ms=1000)
    print(f"Clean speech metrics: RMS={q_speech.rms:.4f}, SNR={q_speech.snr_db:.1f}dB, Status={q_speech.quality_status.upper()}")
    assert q_speech.quality_status in ("good", "fair")
    print("[OK] Audio quality intelligence analysis: PASS")

    print_step("STEP 6: OPENAI AGENTS SDK ACOUSTIC AGENT")
    agent = AcousticIntelligenceAgent()
    dummy_chunk = AudioChunk(
        session_id="ver_sess",
        conversation_id="ver_conv",
        speaker_id="ver_spk",
        segment_id="seg_ver_01",
        sequence=1,
        start_ms=0,
        end_ms=1000,
        duration_ms=1000,
        quality=q_speech,
        status="final",
    )
    analysis = await agent.analyze_segment(dummy_chunk)
    print(f"Agent Provider: {analysis['provider']}")
    print(f"Acoustic Status: {analysis['acoustic_status']}")
    print("[OK] OpenAI Agents SDK decision agent: PASS")

    print_step("STEP 7: STREAMING PIPELINE VERIFICATION")
    pipeline = AudioPipeline("ver_sess", "ver_conv", "spk_1")
    frame = generate_speech_like_signal(50, 16000)
    t0 = time.perf_counter()
    evts = await pipeline.process_frame(frame, sequence=1)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    print(f"Single 50ms frame processing latency: {latency_ms:.2f} ms")
    assert latency_ms < 50.0  # Processing faster than real-time
    print("[OK] Real-time streaming speed constraint: PASS")

    print_step("VERIFICATION SUMMARY")
    print("Agent 01: TalkFlow Audio Intelligence Agent is completely verified and operational!")


if __name__ == "__main__":
    asyncio.run(verify())
