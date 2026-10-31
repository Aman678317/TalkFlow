"""Unit tests for faster-whisper real model execution."""
from pathlib import Path
from app.audio.conversion import wav_bytes_to_pcm16
from app.providers.faster_whisper.provider import FasterWhisperProvider
from tests.fixtures.audio_fixtures import generate_silence


def test_faster_whisper_availability_and_languages():
    provider = FasterWhisperProvider(model_size="base", device="cpu", compute_type="int8")
    assert provider.is_available() is True
    langs = provider.supported_languages()
    assert "en" in langs
    assert "hi" in langs
    assert "mr" in langs


def test_faster_whisper_transcribe_real_audio():
    provider = FasterWhisperProvider(model_size="base", device="cpu", compute_type="int8", cpu_threads=4)

    sample_path = Path(__file__).parent.parent / "fixtures" / "en_example.wav"
    assert sample_path.exists()

    with open(sample_path, "rb") as f:
        wav_bytes = f.read()

    pcm16, sr, _ = wav_bytes_to_pcm16(wav_bytes)

    # Transcribe first 3 seconds of real speech
    chunk_3s = pcm16[: 16000 * 2 * 3]
    result = provider.transcribe(chunk_3s, sample_rate=16000, word_timestamps=True)

    assert result.text != ""
    assert result.language == "en"
    assert result.language_probability > 0.8
    assert result.duration_ms > 0
    assert len(result.segments) >= 1
    assert len(result.words) >= 1


def test_faster_whisper_silence_returns_empty():
    provider = FasterWhisperProvider(model_size="base", device="cpu", compute_type="int8", cpu_threads=4)
    silence = generate_silence(duration_sec=1.0)
    result = provider.transcribe(silence, sample_rate=16000)
    # Silence should not hallucinate
    assert result.text == ""

