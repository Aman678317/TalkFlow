"""Terminal demonstration script processing a WAV audio file through the Audio Intelligence Agent."""
import argparse
import asyncio
import sys
import time
from pathlib import Path

# Ensure package on path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import soundfile as sf
from app.audio.normalization import AudioNormalizer
from app.core.config import settings
from app.services.pipeline import AudioPipeline


def format_log(msg: str):
    print(f"[INFO] {msg}")


async def run_demo(wav_path: str, session_id: str = "meeting_123", speaker_id: str = "user_001"):
    file_path = Path(wav_path)
    if not file_path.exists():
        # Fallback to test fixture
        alt_path = Path(__file__).parent.parent / "tests" / "fixtures" / "en_example.wav"
        if alt_path.exists():
            file_path = alt_path
        else:
            print(f"Error: audio file {wav_path} not found.")
            return

    format_log("Audio Intelligence Agent started.")
    format_log(f"Session created: {session_id}")

    # Read and normalize audio
    data, sr = sf.read(str(file_path), dtype="int16")
    normalizer = AudioNormalizer()
    pcm = normalizer.normalize(data.tobytes(), source_sample_rate=sr)

    total_duration_ms = len(pcm) // 32
    format_log(f"Audio received: PCM16 / 16 kHz / 50 ms (Total: {total_duration_ms} ms)")

    pipeline = AudioPipeline(
        session_id=session_id,
        conversation_id=session_id,
        speaker_id=speaker_id,
    )

    frame_size_bytes = 1600  # 50 ms @ 16 kHz mono int16
    offset = 0
    seq = 0
    noise_analyzed = False

    while offset < len(pcm):
        t0 = time.perf_counter()
        frame = pcm[offset:offset + frame_size_bytes]
        if len(frame) < frame_size_bytes:
            frame = frame.ljust(frame_size_bytes, b"\x00")

        events = await pipeline.process_frame(frame, sequence=seq)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        if not noise_analyzed and seq == 2:
            format_log("Noise analysis completed.")
            noise_analyzed = True

        for evt, pcm_chunk in events:
            evt_type = evt.get("event")

            if evt_type == "speech.started":
                format_log("VAD: Speech detected.")
                format_log(f"Speech started: speaker {speaker_id}")

            elif evt_type == "audio.segment.partial":
                format_log(f"Partial segment emitted ({evt['duration_ms']} ms).")

            elif evt_type == "speech.ended":
                format_log("Speech pause detected.")

            elif evt_type == "audio.segment.final":
                format_log(f"Final audio segment committed: {evt['segment_id']} ({evt['duration_ms']} ms).")
                q_status = evt.get("quality", {}).get("quality_status", "UNKNOWN").upper()
                format_log(f"Quality status: {q_status}")
                format_log("Sending segment to downstream STT agent.")
                format_log(f"Processing latency: {latency_ms:.1f} ms")

        offset += frame_size_bytes
        seq += 1
        # Realistic stream cadence simulation
        await asyncio.sleep(0.01)

    # Flush remainder
    flush_evts = pipeline.flush()
    for evt, pcm_chunk in flush_evts:
        if evt.get("event") == "audio.segment.final":
            format_log(f"Final audio segment committed: {evt['segment_id']} ({evt['duration_ms']} ms).")
            q_status = evt.get("quality", {}).get("quality_status", "UNKNOWN").upper()
            format_log(f"Quality status: {q_status}")
            format_log("Sending segment to downstream STT agent.")

    format_log("Terminal audio processing demonstration completed successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Terminal demonstration for TalkFlow Audio Intelligence Agent")
    parser.add_argument("--file", "-f", default="tests/fixtures/en_example.wav", help="Path to input WAV file")
    parser.add_argument("--session", "-s", default="meeting_123", help="Session ID")
    parser.add_argument("--speaker", "-p", default="user_001", help="Speaker ID")
    args = parser.parse_args()

    asyncio.run(run_demo(args.file, args.session, args.speaker))

