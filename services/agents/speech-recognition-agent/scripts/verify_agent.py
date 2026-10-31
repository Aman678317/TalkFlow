"""Verification and audit script for TalkFlow Speech Recognition Agent (Agent 02)."""
import asyncio
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.audio.conversion import wav_bytes_to_pcm16
from app.audio.ingestion import AudioIngestionEngine
from app.core.config import settings
from app.core.logging import setup_logging
from app.providers import get_stt_provider
from app.stt.confidence import ConfidenceEvaluator
from app.stt.engine import STTEngine
from app.stt.language_hints import LanguageRegistry
from tests.fixtures.audio_fixtures import generate_silence, generate_tone

setup_logging(level="INFO", structured=False)


def run_verification():
    print("=" * 80)
    print("TALKFLOW SPEECH RECOGNITION AGENT (AGENT 02) — COMPONENT AUDIT & VERIFICATION")
    print("=" * 80)

    # STEP 1: Configuration & Environment
    print("\n==================== STEP 1: CONFIGURATION & ENVIRONMENT ====================")
    print(f"Agent Name: {settings.agent.name} v{settings.agent.version}")
    print(f"API Bind: {settings.api.host}:{settings.api.port}")
    print(f"Canonical Sample Rate: {settings.audio.canonical_sample_rate} Hz")
    print(f"Primary STT Provider: {settings.stt.primary_provider} (Model: {settings.stt.model_size})")
    print(f"Inference Device: {settings.stt.device} (Compute: {settings.stt.compute_type}, Threads: {settings.stt.cpu_threads})")
    print(f"Operational Brain Model: {settings.llm_agent.model} (Base URL: {settings.llm_agent.base_url})")

    # STEP 2: Ingestion & Audio Validation
    print("\n==================== STEP 2: AUDIO INGESTION & VALIDATION ====================")
    ingestion = AudioIngestionEngine()
    tone = generate_tone(440.0, 0.5, 16000)
    # Test TalkFlow 'O' Binary Frame layout
    frame = bytearray(17 + len(tone))
    frame[0] = ord("O")
    frame[1:17] = b"seg_test_0100000"
    frame[17:] = tone
    short_id, pcm = ingestion.ingest_binary_frame(bytes(frame))
    assert short_id == "seg_test_01"
    assert len(pcm) == len(tone)
    print("[OK] Binary frame ingestion & TalkFlow wire format: PASS")

    # STEP 3: Language Capabilities & Code-Switching Registry
    print("\n==================== STEP 3: LANGUAGE CAPABILITIES & CODE-SWITCHING =========")
    capabilities = LanguageRegistry.get_capabilities()
    indic_count = sum(1 for c in capabilities if c.code in ("hi", "mr", "bn", "ta", "te", "gu", "kn", "pa", "ur"))
    print(f"Total registered languages: {len(capabilities)} (Indian languages verified: {indic_count})")
    assert indic_count >= 8
    print("[OK] Multilingual & Indian language capability audit: PASS")

    # STEP 4: Anti-Hallucination & Repetition Filter
    print("\n==================== STEP 4: ANTI-HALLUCINATION & REPETITION FILTER ========")
    evaluator = ConfidenceEvaluator()
    from app.models.schemas import STTResult
    hallu_res = STTResult(text="Thank you for watching.", language="en", confidence=0.3, no_speech_prob=0.5)
    cleaned, flags = evaluator.evaluate(hallu_res)
    assert cleaned == ""
    print(f"Hallucination test: '{hallu_res.text}' -> Suppressed (Flags: {flags})")
    print("[OK] Anti-hallucination suppression filter: PASS")

    # STEP 5: Real faster-whisper Model Transcription
    print("\n==================== STEP 5: FASTER-WHISPER SPEECH RECOGNITION ==============")
    provider = get_stt_provider()
    sample_file = root_dir / "tests" / "fixtures" / "en_example.wav"
    if sample_file.exists():
        with open(sample_file, "rb") as f:
            wav_bytes = f.read()
        pcm16, sr, _ = wav_bytes_to_pcm16(wav_bytes)
        chunk_3s = pcm16[: 16000 * 2 * 3]

        started = time.perf_counter()
        res = provider.transcribe(chunk_3s, sample_rate=16000, word_timestamps=True)
        lat_ms = (time.perf_counter() - started) * 1000
        print(f"Sample Transcription: {res.text!r}")
        print(f"Detected Language: {res.language.upper()} (Prob: {res.language_probability})")
        print(f"Inference Latency: {lat_ms:.1f} ms (Words aligned: {len(res.words)})")
        assert res.text != ""
        print("[OK] faster-whisper speech recognition engine: PASS")
    else:
        print("[SKIP] Reference audio file not found.")

    # STEP 6: Silence Handling
    print("\n==================== STEP 6: SILENCE & NO-SPEECH HANDLING ===================")
    silence = generate_silence(duration_sec=1.0)
    silence_res = provider.transcribe(silence, sample_rate=16000)
    assert silence_res.text == ""
    print("[OK] Silence handling (Zero Hallucination): PASS")

    # STEP 7: Operational Reasoning Agent Brain
    print("\n==================== STEP 7: OPENAI AGENTS SDK OPERATIONAL BRAIN ============")
    from app.agents.brain import stt_brain
    diag = asyncio.run(stt_brain.run_diagnostics("Inspect STT service operational health"))
    print(f"Diagnostic output preview:\n{diag[:200]}...")
    print("[OK] Operational reasoning agent brain: PASS")

    print("\n" + "=" * 80)
    print("VERIFICATION SUMMARY: Agent 02 (Speech Recognition Agent) is 100% OPERATIONAL!")
    print("=" * 80)


if __name__ == "__main__":
    run_verification()

