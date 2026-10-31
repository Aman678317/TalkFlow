"""Performance and concurrency scaling tests for Speech Recognition Agent."""
import asyncio
import time
import pytest
from app.providers.fallback.mock_provider import MockSTTProvider
from app.stt.engine import STTEngine
from tests.fixtures.audio_fixtures import generate_tone


@pytest.mark.asyncio
async def test_concurrent_transcriptions_scaling():
    provider = MockSTTProvider(default_text="concurrency benchmark transcript")
    engine = STTEngine(provider=provider)

    audio = generate_tone(440.0, 1.0, 16000)

    async def transcribe_job(session_idx: int):
        started = time.perf_counter()
        resp = await engine.transcribe_segment_async(
            audio_pcm16=audio,
            session_id=f"bench_sess_{session_idx}",
            conversation_id="bench_conv",
            speaker_id="bench_speaker",
            utterance_id=f"utt_{session_idx}",
            segment_id=f"seg_{session_idx}",
            seq=session_idx,
            start_ms=0,
            sample_rate=16000,
        )
        latency = (time.perf_counter() - started) * 1000
        return latency, resp

    # Test scaling at C = 1, 2, 4, 8, 16 concurrent requests
    for concurrency in [1, 2, 4, 8, 16]:
        tasks = [transcribe_job(i) for i in range(concurrency)]
        results = await asyncio.gather(*tasks)

        latencies = [r[0] for r in results]
        mean_lat = sum(latencies) / len(latencies)
        assert len(results) == concurrency
        assert mean_lat < 500  # Mock/fast provider runs in sub-100ms

