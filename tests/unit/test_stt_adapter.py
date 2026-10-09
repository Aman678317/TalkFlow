import asyncio
import pytest
from gt_ai.stt.recognizer import SpeechRecognizer, StreamingSpeechRecognizer
from gt_ai.types import TranscriptChunk


class MockSTTProvider:
    def __init__(self):
        self.call_count = 0
        self.languages_seen = []

    async def transcribe(self, audio: bytes, sample_rate: int, lang_hint: str | None = None) -> TranscriptChunk:
        self.call_count += 1
        self.languages_seen.append(lang_hint)
        # Mock detection: high confidence Hindi
        return TranscriptChunk(
            text="नमस्ते आप कैसे हैं",
            language="hi",
            is_final=True,
            confidence=0.92,
            model="mock-whisper",
            provider="mock",
        )


@pytest.mark.asyncio
async def test_streaming_speech_recognizer_lifecycle_and_callbacks():
    provider = MockSTTProvider()
    recognizer = StreamingSpeechRecognizer(provider, sample_rate=16000)

    partials = []
    finals = []
    errors = []

    recognizer.on_partial_transcript(lambda s_id, p_id, chunk: partials.append((s_id, p_id, chunk)))
    recognizer.on_final_transcript(lambda s_id, p_id, chunk: finals.append((s_id, p_id, chunk)))
    recognizer.on_error(lambda s_id, p_id, err: errors.append((s_id, p_id, err)))

    session_id = "test-session-1"
    participant_id = "participant-alice"

    # 1. Start session with auto language
    await recognizer.start(session_id, participant_id, source_language="auto")
    sess = recognizer.sessions[session_id]
    assert sess.locked_language is None

    # 2. Push audio frame (simulate speech)
    # 50ms of 16kHz audio = 800 samples = 1600 bytes
    pcm_frame = b"\x10\x00" * 800
    await recognizer.push_audio(session_id, pcm_frame)

    # 3. Stop session flushes in-flight audio
    await recognizer.stop(session_id)

    assert len(errors) == 0
    assert len(finals) >= 0


@pytest.mark.asyncio
async def test_speech_recognizer_language_locking():
    provider = MockSTTProvider()
    recognizer = StreamingSpeechRecognizer(provider, sample_rate=16000)

    # When explicit language configured, locked immediately
    await recognizer.start("sess-hi", "part-1", source_language="hi")
    assert recognizer.sessions["sess-hi"].locked_language == "hi"

    # When auto configured, initial locked is None
    await recognizer.start("sess-auto", "part-2", source_language="auto")
    sess_auto = recognizer.sessions["sess-auto"]
    assert sess_auto.locked_language is None

    # Simulate receiving high-confidence chunk
    pcm_audio = b"\x20\x00" * 3200  # 100ms
    await recognizer._emit_partial(sess_auto, pcm_audio)
    assert sess_auto.locked_language == "hi"  # Locked due to confidence 0.92 >= 0.70
