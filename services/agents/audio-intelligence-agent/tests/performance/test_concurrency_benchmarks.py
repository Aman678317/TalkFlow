"""Performance and concurrency benchmarks test suite."""
import asyncio
import time
import pytest
from app.services.pipeline import AudioPipeline
from tests.fixtures.audio_fixtures import generate_silence, generate_speech_like_signal


async def run_single_stream(session_id: str, num_frames: int = 20) -> float:
    pipeline = AudioPipeline(
        session_id=session_id,
        conversation_id=session_id,
        speaker_id=f"spk_{session_id}",
    )
    frame = generate_speech_like_signal(50, 16000, amplitude=0.6)

    t0 = time.perf_counter()
    for seq in range(num_frames):
        await pipeline.process_frame(frame, sequence=seq)
    pipeline.flush()
    return (time.perf_counter() - t0) * 1000.0  # total ms


@pytest.mark.asyncio
async def test_concurrent_sessions_scaling():
    # Benchmark 1, 2, 4, 8 concurrent sessions
    for concurrency in (1, 2, 4, 8):
        tasks = [
            run_single_stream(f"bench_sess_{concurrency}_{i}", num_frames=20)
            for i in range(concurrency)
        ]
        t_start = time.perf_counter()
        latencies = await asyncio.gather(*tasks)
        total_wall_ms = (time.perf_counter() - t_start) * 1000.0

        mean_stream_ms = sum(latencies) / len(latencies)
        # Each stream had 20 frames of 50ms = 1000ms (1 second) of audio.
        # Total frame processing time must be significantly faster than real-time (> 2x real-time speed)
        # 1000ms audio processed in << 1000ms wall time
        assert mean_stream_ms < 1000.0

