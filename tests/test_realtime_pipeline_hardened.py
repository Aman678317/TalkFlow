"""Phase 5 Verification Test Suite: Realtime Translation Pipeline Reliability & Canonical Fan-out:
1. Canonical source segment invariant:
   Human speech/text -> canonical immutable source -> independent target fan-out.
   NO translation chaining (e.g. Hindi -> English -> Japanese).
2. STT degradation:
   STT failure -> original audio continues, error emitted, NO fabricated transcript.
3. MT degradation:
   MT failure -> original captions remain, translation.failed emitted, NO fabricated translation.
4. TTS degradation:
   TTS failure -> translated captions remain, error emitted, NO fabricated audio.
5. Audio queue backpressure & quality degradation.
6. Stale audio suppression & speaker sequence ordering.
7. Multilingual chat canonical fan-out & non-fabrication.
"""
from __future__ import annotations

import asyncio
import uuid
import pytest
from unittest.mock import AsyncMock, patch

from app.db import models as M
from app.db.session import db_session
from app.realtime import pipeline as pl
from app.realtime.protocol import ServerEventType
from app.realtime.session_manager import RtParticipant, RtSession, manager
from app.services import chat_service
from gt_ai.types import (
    Intent,
    TranscriptChunk,
    RouteDecision,
    TranslationResult,
    AudioChunk,
)


@pytest.fixture
async def sample_rt_session(services_app_client, user):
    """Fixture creating a real meeting and corresponding realtime session."""
    res = services_app_client.post(
        "/api/v1/meetings",
        headers=user["headers"],
        json={"title": "Pipeline Test Meeting", "mode": "ws", "hear_lang": "en"},
    )
    assert res.status_code == 201
    meeting_id = uuid.UUID(res.json()["id"])
    org_id = uuid.UUID(user["org_id"])

    session = await manager.create_session(
        meeting_id=meeting_id,
        org_id=org_id,
        room_name=f"test-pipeline-{uuid.uuid4().hex[:6]}",
        mode="ws",
    )
    yield session
    await manager.close_session(session.session_id)


@pytest.mark.asyncio
async def test_canonical_source_segment_and_independent_fanout(sample_rt_session):
    """Verify that speech commits an immutable canonical source segment and
    independently fans out to distinct target languages without chaining.
    """
    session = sample_rt_session
    pipe = pl.get_pipeline(session)

    # Speaker (English)
    speaker_id = uuid.uuid4()
    speaker = RtParticipant(
        participant_id=speaker_id,
        user_id=uuid.uuid4(),
        display_name="Alice (Speaker)",
        speak_lang="en",
        hear_lang="en",
        connected=True,
    )
    manager.add_participant(session, speaker)

    # Listener 1: Spanish
    l1_id = uuid.uuid4()
    l1 = RtParticipant(
        participant_id=l1_id,
        user_id=uuid.uuid4(),
        display_name="Bob (Spanish)",
        speak_lang="es",
        hear_lang="es",
        audio_mode="translated",
        connected=True,
    )
    manager.add_participant(session, l1)

    # Listener 2: French
    l2_id = uuid.uuid4()
    l2 = RtParticipant(
        participant_id=l2_id,
        user_id=uuid.uuid4(),
        display_name="Claire (French)",
        speak_lang="fr",
        hear_lang="fr",
        audio_mode="translated",
        connected=True,
    )
    manager.add_participant(session, l2)

    # Track translation calls to verify independent fan-out from canonical source
    translation_calls = []

    async def mock_translate_text(db, text, source_lang, target_lang, ctx):
        translation_calls.append((text, source_lang, target_lang))
        from app.services.translation_service import TranslateOutput
        res = TranslationResult(
            text=f"[{target_lang}] {text}",
            source_lang=source_lang,
            target_lang=target_lang,
            model="test_model",
            provider="test_provider",
        )
        return TranslateOutput(
            result=res,
            translation_id=uuid.uuid4(),
            tm_match=None,
            source_lang=source_lang,
        )

    with patch("app.realtime.pipeline.translate_text", side_effect=mock_translate_text):
        # Inject canonical transcript segment
        await pipe.inject_transcript(speaker, "Hello global team, welcome!", language="en")
        # Allow async fan-out tasks to execute
        await asyncio.sleep(0.1)

    # 1. Canonical source segment must be stored in database
    async with db_session() as db:
        from sqlalchemy import select
        res = await db.execute(
            select(M.TranscriptSegment).where(M.TranscriptSegment.meeting_id == session.meeting_id)
        )
        segments = res.scalars().all()
        assert len(segments) == 1
        seg = segments[0]
        assert seg.source_text == "Hello global team, welcome!"
        assert seg.source_lang == "en"
        assert seg.speaker_id == speaker_id

    # 2. Independent fan-out: both target languages were translated directly from original source
    assert len(translation_calls) == 2
    targets_called = {call[2] for call in translation_calls}
    assert targets_called == {"es", "fr"}
    for call in translation_calls:
        # Source text is ALWAYS the human original, never a previous translation
        assert call[0] == "Hello global team, welcome!"
        assert call[1] == "en"


@pytest.mark.asyncio
async def test_stt_failure_graceful_degradation(sample_rt_session):
    """When STT fails, no fabricated transcript is created, and an error is broadcast."""
    session = sample_rt_session
    pipe = pl.get_pipeline(session)

    speaker = RtParticipant(
        participant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        display_name="Speaker",
        speak_lang="en",
        hear_lang="en",
        connected=True,
    )
    manager.add_participant(session, speaker)

    broadcasted_events = []

    async def mock_broadcast(sess, ev_type, data=None, **kwargs):
        broadcasted_events.append((ev_type, data))

    u = pl.UtteranceState(
        participant_id=speaker.participant_id,
        buffer=bytearray(b"\x00\x01" * 2000),  # Valid audio length > 1600 bytes
        capture_started=0.0,
    )

    with patch("app.ai.ai.transcribe", side_effect=RuntimeError("Whisper model out of memory")), \
         patch.object(manager, "broadcast", side_effect=mock_broadcast):
        await pipe._finalize_utterance(speaker, u)

    # Error must be broadcast informing that STT is unavailable
    error_events = [e for e in broadcasted_events if e[0] == ServerEventType.ERROR]
    assert len(error_events) == 1
    assert error_events[0][1]["code"] == "stt_unavailable"
    assert error_events[0][1]["recoverable"] is True

    # No transcript final must be emitted
    final_events = [e for e in broadcasted_events if e[0] == ServerEventType.TRANSCRIPT_FINAL]
    assert len(final_events) == 0

    # No segment committed to database
    async with db_session() as db:
        from sqlalchemy import select
        res = await db.execute(
            select(M.TranscriptSegment).where(M.TranscriptSegment.meeting_id == session.meeting_id)
        )
        assert len(res.scalars().all()) == 0


@pytest.mark.asyncio
async def test_mt_failure_graceful_degradation(sample_rt_session):
    """When MT fails, original captions remain active, translation.failed is broadcast,
    and no fabricated translation is generated.
    """
    session = sample_rt_session
    pipe = pl.get_pipeline(session)

    speaker = RtParticipant(
        participant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        display_name="Host",
        speak_lang="en",
        hear_lang="en",
        connected=True,
    )
    manager.add_participant(session, speaker)

    listener = RtParticipant(
        participant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        display_name="German Listener",
        speak_lang="de",
        hear_lang="de",
        connected=True,
    )
    manager.add_participant(session, listener)

    broadcasted_events = []

    async def mock_broadcast(sess, ev_type, data=None, **kwargs):
        broadcasted_events.append((ev_type, data))

    with patch("app.realtime.pipeline.translate_text", side_effect=Exception("Translation service down")), \
         patch.object(manager, "broadcast", side_effect=mock_broadcast):
        await pipe.inject_transcript(speaker, "Crucial announcement", language="en")
        await asyncio.sleep(0.1)

    # Original transcript final was broadcast
    final_events = [e for e in broadcasted_events if e[0] == ServerEventType.TRANSCRIPT_FINAL]
    assert len(final_events) == 1
    assert final_events[0][1]["text"] == "Crucial announcement"

    # Translation failed event was broadcast
    failed_events = [e for e in broadcasted_events if e[0] == ServerEventType.TRANSLATION_FAILED]
    assert len(failed_events) == 1
    assert failed_events[0][1]["target_lang"] == "de"
    assert failed_events[0][1]["recoverable"] is True

    # No translation final or fake translation
    trans_final = [e for e in broadcasted_events if e[0] == ServerEventType.TRANSLATION_FINAL]
    assert len(trans_final) == 0


@pytest.mark.asyncio
async def test_tts_failure_graceful_degradation(sample_rt_session):
    """When TTS fails, translated captions continue to display, tts_unavailable error
    is broadcast, and no fabricated audio chunks are emitted.
    """
    session = sample_rt_session
    pipe = pl.get_pipeline(session)

    speaker = RtParticipant(
        participant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        display_name="Host",
        speak_lang="en",
        hear_lang="en",
        connected=True,
    )
    manager.add_participant(session, speaker)

    listener = RtParticipant(
        participant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        display_name="Audio Listener",
        speak_lang="es",
        hear_lang="es",
        audio_mode="translated",
        connected=True,
    )
    manager.add_participant(session, listener)

    broadcasted_events = []

    async def mock_broadcast(sess, ev_type, data=None, **kwargs):
        broadcasted_events.append((ev_type, data))

    with patch("app.ai.ai.synthesize_stream", side_effect=RuntimeError("TTS engine failed")), \
         patch.object(manager, "broadcast", side_effect=mock_broadcast):
        await pipe.inject_transcript(speaker, "Hello world", language="en")
        for _ in range(30):
            if any(e[0] == ServerEventType.TRANSLATION_FINAL for e in broadcasted_events):
                break
            await asyncio.sleep(0.05)

    # Translated captions were broadcast successfully
    trans_final = [e for e in broadcasted_events if e[0] == ServerEventType.TRANSLATION_FINAL]
    assert len(trans_final) == 1

    # TTS unavailable error was broadcast
    tts_err = [e for e in broadcasted_events if e[0] == ServerEventType.ERROR and e[1].get("code") == "tts_unavailable"]
    assert len(tts_err) == 1

    # No audio chunks emitted
    audio_chunks = [e for e in broadcasted_events if e[0] == ServerEventType.TTS_CHUNK]
    assert len(audio_chunks) == 0


@pytest.mark.asyncio
async def test_audio_backpressure_drops_chunks_and_signals_degraded(sample_rt_session):
    """When incoming audio exceeds queue capacity, backpressure drops oldest chunks
    and broadcasts QUALITY_DEGRADED.
    """
    session = sample_rt_session
    pipe = pl.get_pipeline(session)

    speaker = RtParticipant(
        participant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        display_name="Speaker",
        speak_lang="en",
        hear_lang="en",
        connected=True,
    )
    manager.add_participant(session, speaker)
    pipe.start_speaker(speaker)

    # Fill queue to maximum capacity
    queue = pipe.audio_queues[speaker.participant_id]
    dummy_chunk = b"\x00\x00" * 800  # 100ms PCM16
    for _ in range(pl.AUDIO_QUEUE_MAX):
        queue.put_nowait(dummy_chunk)

    broadcasted_events = []

    async def mock_broadcast(sess, ev_type, data=None, **kwargs):
        broadcasted_events.append((ev_type, data))

    with patch.object(manager, "broadcast", side_effect=mock_broadcast):
        # Feeding another chunk must trigger backpressure drop
        await pipe.feed_audio(speaker.participant_id, dummy_chunk)

    assert session.quality_degraded is True
    degraded = [e for e in broadcasted_events if e[0] == ServerEventType.QUALITY_DEGRADED]
    assert len(degraded) == 1
    assert degraded[0][1]["reason"] == "audio_backpressure"

    pipe.stop_speaker(speaker.participant_id)
    await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_stale_audio_rejection_prevents_overlap(sample_rt_session):
    """When a speaker finishes a newer segment, older in-flight segments are
    classified as stale and dropped to prevent late audio overlap.
    """
    session = sample_rt_session
    pipe = pl.get_pipeline(session)
    speaker_id = uuid.uuid4()

    # If latest seq is 5, seq 3 is stale
    pipe._latest_final_seq[speaker_id] = 5
    assert pipe._is_stale(speaker_id, 3) is True
    assert pipe._is_stale(speaker_id, 4) is True
    assert pipe._is_stale(speaker_id, 5) is False
    assert pipe._is_stale(speaker_id, 6) is False


@pytest.mark.asyncio
async def test_multilingual_chat_canonical_fanout_and_no_fabrication(services_app_client, user):
    """Verify chat messages preserve immutable canonical text and independently
    fan out translations to all participant languages.
    """
    res = services_app_client.post(
        "/api/v1/meetings",
        headers=user["headers"],
        json={"title": "Chat Test Meeting", "mode": "ws", "hear_lang": "en"},
    )
    assert res.status_code == 201
    meeting_id = uuid.UUID(res.json()["id"])

    async with db_session() as db:
        meeting = await db.get(M.Meeting, meeting_id)
        sender = (await db.execute(
            M.Participant.__table__.select().where(M.Participant.meeting_id == meeting_id)
        )).first()

        # Send chat message with multiple target languages
        msg = await chat_service.send_message(
            db,
            meeting=meeting,
            sender=sender,
            text="Hello everyone in the meeting",
            target_langs=["es", "fr", "de"],
            org_id=meeting.org_id,
            user_id=sender.user_id,
        )

        assert msg.original_text == "Hello everyone in the meeting"
        assert msg.detected_lang == "en"
        assert "es" in msg.translations_json
        assert "fr" in msg.translations_json
        assert "de" in msg.translations_json

        # In dev mode, each target gets a valid translated dictionary
        for tgt in ("es", "fr", "de"):
            assert msg.translations_json[tgt]["text"] is not None
            assert msg.translations_json[tgt]["model"] is not None
