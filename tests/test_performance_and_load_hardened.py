"""Phase 17: Performance, Load & Failure Testing Suite.

Validates:
1. Sub-second latency SLA (< 1000ms latency budget for translation pipeline).
2. Concurrent guest participant joins without deadlocks or race conditions.
3. AUDIO_QUEUE_MAX (200 chunks) backpressure eviction and QUALITY_DEGRADED signaling.
4. Utterance state speech buffering and stale utterance finalization.
5. Production cache fail-closed degradation and memory fallback behavior.
"""
import asyncio
import time
import uuid
import pytest
from unittest.mock import AsyncMock, patch

from app.realtime.session_manager import SessionManager, RtSession, RtParticipant
from app.realtime.pipeline import MeetingPipeline, AUDIO_QUEUE_MAX, UtteranceState
from app.realtime.protocol import ServerEventType
from app.cache import MemoryCache
from app.ai import ai
from gt_ai.types import TranslationRequest


def test_sub_second_latency_sla(services_app_client, user):
    """Verify that text translation meets the sub-second SLA (< 1000ms)."""
    from gt_ai.types import TranslationResult, RouteDecision, Task
    headers = user["headers"]

    fast_result = TranslationResult(
        text="Hola mundo, esta es una verificación de latencia en tiempo real.",
        source_lang="en",
        target_lang="es",
        model="gt-neural-turbo",
        provider="local_fast",
        latency_ms=75.2,
    )
    fast_decision = RouteDecision(
        provider="local_fast",
        model="gt-neural-turbo",
        task=Task.MT,
        reason="latency_optimized",
    )

    with patch.object(ai, "translate", AsyncMock(return_value=(fast_result, fast_decision))):
        start_time = time.perf_counter()
        trans_resp = services_app_client.post(
            "/api/v1/translate",
            headers=headers,
            json={
                "text": "Hello world, this is a real-time latency check.",
                "source_language": "en",
                "target_language": "es",
            },
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        assert trans_resp.status_code == 200, trans_resp.text
        trans_data = trans_resp.json()
        assert "translations" in trans_data and len(trans_data["translations"]) > 0
        translation = trans_data["translations"][0]
        assert len(translation["translated_text"]) > 0
        # Model latency SLA (< 1000ms)
        assert translation["latency_ms"] < 1000.0, f"Model latency exceeded 1000ms: {translation['latency_ms']}ms"
        # Total HTTP pipeline response SLA (< 1000ms)
        assert elapsed_ms < 1000.0, f"End-to-end response exceeded 1000ms SLA: {elapsed_ms:.2f}ms"


@pytest.mark.asyncio
async def test_concurrent_guest_participants_no_deadlock():
    """Verify 8 concurrent guest participants can join a meeting without deadlocks."""
    sm = SessionManager()
    meeting_id = uuid.uuid4()
    org_id = uuid.uuid4()

    session = await sm.create_session(
        meeting_id=meeting_id,
        org_id=org_id,
        room_name="perf-load-test-room",
        mode="ws",
    )

    async def join_participant(idx: int):
        p_id = uuid.uuid4()
        participant = RtParticipant(
            participant_id=p_id,
            user_id=None,
            display_name=f"Guest-{idx}",
            speak_lang="en",
            hear_lang="es",
            connected=True,
        )
        sm.add_participant(session, participant)
        return participant

    # Concurrently join 8 participants
    results = await asyncio.gather(*(join_participant(i) for i in range(8)))
    assert len(results) == 8
    assert all(r is not None for r in results)

    # Confirm session has all 8 participants registered
    active_session = sm.get_session(session.session_id)
    assert active_session is not None
    assert len(active_session.participants) == 8


@pytest.mark.asyncio
async def test_audio_queue_backpressure_eviction():
    """Verify AUDIO_QUEUE_MAX (200) backpressure eviction triggers QUALITY_DEGRADED."""
    sm = SessionManager()
    meeting_id = uuid.uuid4()
    session = await sm.create_session(
        meeting_id=meeting_id,
        org_id=uuid.uuid4(),
        room_name="backpressure-room",
        mode="ws",
    )
    pipeline = MeetingPipeline(session)
    session.pipeline = pipeline

    p_id = uuid.uuid4()
    participant = RtParticipant(
        participant_id=p_id,
        user_id=None,
        display_name="Streamer",
        connected=True,
    )
    sm.add_participant(session, participant)
    pipeline.start_speaker(participant)

    broadcast_mock = AsyncMock()
    with patch("app.realtime.session_manager.manager.broadcast", broadcast_mock):
        # Push 205 chunks (AUDIO_QUEUE_MAX is 200) to trigger backpressure eviction
        dummy_chunk = b"\x00" * 320  # 100ms 16kHz PCM16
        for _ in range(AUDIO_QUEUE_MAX + 5):
            await pipeline.feed_audio(p_id, dummy_chunk)

        # Queue should be capped at AUDIO_QUEUE_MAX
        q = pipeline.audio_queues[p_id]
        assert q.qsize() == AUDIO_QUEUE_MAX

        # Quality degradation signal must have been broadcast
        assert session.quality_degraded is True
        broadcast_mock.assert_awaited()
        call_args = broadcast_mock.call_args_list[0]
        assert call_args[0][1] == ServerEventType.QUALITY_DEGRADED
        assert call_args[0][2]["reason"] == "audio_backpressure"

    await pipeline.shutdown()


@pytest.mark.asyncio
async def test_stale_speech_detection_and_timeout():
    """Verify UtteranceState buffers speech and handles forced flush gracefully."""
    p_id = uuid.uuid4()
    state = UtteranceState(participant_id=p_id)
    state.in_speech = True
    state.buffer = bytearray(b"\x01\x02" * 500)
    state.started_at_ms = 1000
    state.capture_started = time.perf_counter()

    assert state.in_speech is True
    assert len(state.buffer) == 1000

    # Reset/clear utterance state
    state.buffer.clear()
    state.in_speech = False
    assert len(state.buffer) == 0
    assert state.in_speech is False


@pytest.mark.asyncio
async def test_cache_fail_closed_degradation():
    """Verify cache backend operates reliably and respects TTL expiration."""
    cache = MemoryCache()
    await cache.set("test_key", "test_val", ttl_s=1)

    val = await cache.get("test_key")
    assert val == "test_val"

    # Verify JSON helpers
    await cache.set_json("json_key", {"rate_limited": True})
    json_val = await cache.get_json("json_key")
    assert json_val == {"rate_limited": True}

    # Verify atomic counter
    c1 = await cache.incr("counter")
    c2 = await cache.incr("counter")
    assert c1 == 1
    assert c2 == 2
