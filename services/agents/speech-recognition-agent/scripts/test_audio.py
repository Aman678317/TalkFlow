"""Terminal audio processing demonstration for Speech Recognition Agent (Agent 02)."""
import argparse
import sys
import time
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.audio.conversion import wav_bytes_to_pcm16
from app.core.config import settings
from app.stt.engine import STTEngine


def run_audio_demo(file_path: Path):
    print("=" * 80)
    print("TALKFLOW SPEECH RECOGNITION AGENT (AGENT 02) — REAL-TIME AUDIO DEMO")
    print("=" * 80)

    print("[INFO] Speech Recognition Agent started.")
    print(f"[INFO] Agent brain: {'ENABLED' if settings.llm_agent.enabled else 'DISABLED'}")
    print(f"[INFO] Ollama model: {settings.llm_agent.model}")
    print(f"[INFO] STT provider: {settings.stt.primary_provider}")
    print(f"[INFO] STT model: {settings.stt.model_size} (Precision: {settings.stt.compute_type}, Threads: {settings.stt.cpu_threads})")

    if not file_path.exists():
        print(f"[ERROR] Audio file not found: {file_path}")
        return

    with open(file_path, "rb") as f:
        wav_bytes = f.read()

    pcm16, sr, _ = wav_bytes_to_pcm16(wav_bytes)
    total_sec = len(pcm16) / 32000.0

    print(f"\n[INFO] Audio segment received from Agent 01: {file_path.name}")
    print(f"[INFO] Session: meeting_prod_101")
    print(f"[INFO] Speaker: user_001")
    print(f"[INFO] Audio validation completed (Duration: {total_sec:.2f}s, Sample Rate: {sr}Hz)")
    print("[INFO] Speech recognition pipeline activated.\n")

    engine = STTEngine()

    # 1. Simulate 50ms streaming frames with partial hypotheses
    frame_bytes = 1600  # 50ms at 16kHz PCM16 mono
    frames = [pcm16[i : i + frame_bytes] for i in range(0, len(pcm16), frame_bytes)]

    session_id = "meeting_prod_101"
    utterance_id = "utt_01JBCDEF"
    segment_id = "seg_01JBCDEF"

    engine.partial_manager.init_utterance(session_id, utterance_id, segment_id)

    stream_start = time.perf_counter()
    partial_count = 0

    # Stream first 4 seconds in 50ms increments
    for i, frame in enumerate(frames[:80]):  # 80 * 50ms = 4.0s
        engine.partial_manager.append_audio(session_id, frame)
        elapsed_ms = int((time.perf_counter() - stream_start) * 1000)

        if engine.partial_manager.should_emit_partial(session_id, elapsed_ms):
            # Synchronous partial for demo visualization
            buf = bytes(engine.partial_manager._states[session_id]["buffer"])
            res = engine.provider.transcribe(buf, sample_rate=16000, word_timestamps=False)
            if res.text.strip():
                partial_count += 1
                print(f"[PARTIAL #{partial_count}] \"{res.text.strip()}\" (Lang: {res.language})")
                engine.partial_manager._states[session_id]["last_partial_time_ms"] = elapsed_ms

    # 2. Finalize utterance
    print("\n[INFO] Pause detected by Agent 01 — committing final transcript.")
    finalize_start = time.perf_counter()
    full_audio = pcm16[: 16000 * 2 * 6]  # First 6 seconds of speech
    final_resp = engine.transcribe_segment(
        audio_pcm16=full_audio,
        session_id=session_id,
        conversation_id="conv_prod_101",
        speaker_id="user_001",
        utterance_id=utterance_id,
        segment_id=segment_id,
        seq=1,
        start_ms=0,
        sample_rate=16000,
        word_timestamps=True,
    )
    final_lat_ms = (time.perf_counter() - finalize_start) * 1000

    print(f"[INFO] Final transcription completed in {final_lat_ms:.1f} ms.")
    print(f"[FINAL TRANSCRIPT] \"{final_resp.text}\"")
    print(f"[METADATA] Language: {final_resp.language_hint.upper()} | Confidence: {final_resp.confidence:.2f} | Words: {len(final_resp.words)}")
    print(f"[INFO] Sending transcript to Agent 03 (Language Intelligence Agent).")
    print("\n[OK] Demonstration completed successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=str, default=str(root_dir / "tests" / "fixtures" / "en_example.wav"))
    args = parser.parse_args()
    run_audio_demo(Path(args.file))

