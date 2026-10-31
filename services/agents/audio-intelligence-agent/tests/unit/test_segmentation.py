"""Unit tests for intelligent speech segmentation and pause handling."""
from app.audio.segmentation import SpeechSegmenter
from tests.fixtures.audio_fixtures import generate_silence, generate_speech_like_signal


def test_speech_start_and_final_commit_on_pause():
    segmenter = SpeechSegmenter(
        speech_threshold=0.5,
        silence_threshold=0.35,
        min_speech_duration_ms=200,
        min_silence_duration_ms=400,
        hangover_duration_ms=300,
    )
    frame_50ms = generate_speech_like_signal(50, 16000)
    silence_50ms = generate_silence(50, 16000)

    clock = 0
    # 1. First speech frame triggers speech.started
    evt, partial, final = segmenter.process_frame(frame_50ms, 0.8, clock, 50)
    assert evt == "speech.started"
    assert partial is None
    assert final is None
    clock += 50

    # 2. Continue speech for 300 ms (6 frames)
    for _ in range(6):
        evt, partial, final = segmenter.process_frame(frame_50ms, 0.85, clock, 50)
        assert final is None
        clock += 50

    # 3. Short pause of 150 ms (3 frames of silence) -> must NOT cut
    for _ in range(3):
        evt, partial, final = segmenter.process_frame(silence_50ms, 0.1, clock, 50)
        assert final is None
        clock += 50

    # 4. Resume speech for 200 ms -> speech continues
    for _ in range(4):
        evt, partial, final = segmenter.process_frame(frame_50ms, 0.8, clock, 50)
        assert final is None
        clock += 50

    # 5. Long pause (min_silence_duration_ms = 400ms -> 8 frames) -> triggers final commitment
    for i in range(7):
        evt, partial, final = segmenter.process_frame(silence_50ms, 0.05, clock, 50)
        clock += 50
        assert final is None

    # The 8th frame reaches 400ms silence
    evt, partial, final = segmenter.process_frame(silence_50ms, 0.05, clock, 50)
    assert evt == "speech.ended"
    assert final is not None
    assert final.total_duration_ms >= 500


def test_short_noise_burst_discarded():
    segmenter = SpeechSegmenter(
        speech_threshold=0.5,
        silence_threshold=0.35,
        min_speech_duration_ms=300,  # 300 ms minimum
        min_silence_duration_ms=200,
    )
    frame_50ms = generate_speech_like_signal(50, 16000)
    silence_50ms = generate_silence(50, 16000)

    clock = 0
    # 100 ms click/cough (2 frames)
    evt, _, _ = segmenter.process_frame(frame_50ms, 0.9, clock, 50)
    assert evt == "speech.started"
    clock += 50
    segmenter.process_frame(frame_50ms, 0.9, clock, 50)
    clock += 50

    # 250 ms silence (5 frames)
    for _ in range(4):
        segmenter.process_frame(silence_50ms, 0.0, clock, 50)
        clock += 50

    evt, partial, final = segmenter.process_frame(silence_50ms, 0.0, clock, 50)
    # Burst was only 100ms (< 300ms min_speech_duration_ms), so final is None (discarded)
    assert final is None


def test_max_utterance_duration_enforcement():
    segmenter = SpeechSegmenter(
        speech_threshold=0.5,
        silence_threshold=0.35,
        max_utterance_duration_ms=1000,  # 1 second max
    )
    frame_50ms = generate_speech_like_signal(50, 16000)

    clock = 0
    committed = False
    # Stream continuous speech for 1100 ms (22 frames)
    for _ in range(22):
        evt, partial, final = segmenter.process_frame(frame_50ms, 0.9, clock, 50)
        clock += 50
        if final is not None:
            committed = True
            assert final.total_duration_ms >= 1000
            break

    assert committed is True

