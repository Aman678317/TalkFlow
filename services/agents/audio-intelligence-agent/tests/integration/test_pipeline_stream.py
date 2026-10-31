"""Integration tests for continuous streaming pipeline and multi-utterance handling."""
from pathlib import Path
import soundfile as sf
import pytest
from app.audio.normalization import AudioNormalizer
from app.services.pipeline import AudioPipeline
from tests.fixtures.audio_fixtures import generate_silence


@pytest.mark.asyncio
async def test_continuous_streaming_pipeline_two_utterances():
    session_id = "test_continuous_sess"
    pipeline = AudioPipeline(
        session_id=session_id,
        conversation_id="conv_main",
        speaker_id="speaker_bob",
    )

    sample_file = Path(__file__).parent.parent / "fixtures" / "en_example.wav"
    data, sr = sf.read(str(sample_file), dtype="int16")
    normalizer = AudioNormalizer()
    real_speech_pcm = normalizer.normalize(data.tobytes(), source_sample_rate=sr)

    frame_silence = generate_silence(50, 16000)
    final_segments = []

    # Utterance 1: 500ms of speech (10 frames of 1600 bytes)
    offset = 16000  # Start at second 0.5 where speech is active
    for seq in range(10):
        frame = real_speech_pcm[offset:offset + 1600]
        events = await pipeline.process_frame(frame, sequence=seq)
        for evt, pcm in events:
            if evt.get("event") == "audio.segment.final":
                final_segments.append(evt)
        offset += 1600

    # Pause 1: 600ms silence (12 frames) -> commits Utterance 1
    for seq in range(10, 22):
        events = await pipeline.process_frame(frame_silence, sequence=seq)
        for evt, pcm in events:
            if evt.get("event") == "audio.segment.final":
                final_segments.append(evt)

    assert len(final_segments) == 1
    assert final_segments[0]["speaker_id"] == "speaker_bob"
    assert final_segments[0]["duration_ms"] >= 400

    # Utterance 2: 400ms speech (8 frames)
    for seq in range(22, 30):
        frame = real_speech_pcm[offset:offset + 1600]
        events = await pipeline.process_frame(frame, sequence=seq)
        for evt, pcm in events:
            if evt.get("event") == "audio.segment.final":
                final_segments.append(evt)
        offset += 1600

    # Pause 2: 600ms silence (12 frames) -> commits Utterance 2
    for seq in range(30, 42):
        events = await pipeline.process_frame(frame_silence, sequence=seq)
        for evt, pcm in events:
            if evt.get("event") == "audio.segment.final":
                final_segments.append(evt)

    assert len(final_segments) == 2
    assert final_segments[1]["segment_id"] != final_segments[0]["segment_id"]
    assert final_segments[1]["sequence"] > final_segments[0]["sequence"]
    assert final_segments[1]["start_ms"] > final_segments[0]["end_ms"]
