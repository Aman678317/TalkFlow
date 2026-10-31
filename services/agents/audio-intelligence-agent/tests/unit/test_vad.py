"""Unit tests for Voice Activity Detection across providers."""
import soundfile as sf
import numpy as np
from pathlib import Path
from app.audio.normalization import AudioNormalizer
from app.providers.vad.energy import EnergyVAD
from app.providers.vad.silero import SileroVAD
from app.providers.vad.webrtc import WebRTCVAD
from tests.fixtures.audio_fixtures import (
    generate_silence,
    generate_speech_like_signal,
    generate_white_noise,
)


def test_energy_vad_silence_vs_speech():
    vad = EnergyVAD()
    silence = generate_silence(duration_ms=100, sample_rate=16000)
    prob_silence = vad.process_chunk(silence, 16000)
    assert prob_silence == 0.0

    speech = generate_speech_like_signal(duration_ms=100, sample_rate=16000, amplitude=0.6)
    prob_speech = vad.process_chunk(speech, 16000)
    assert prob_speech > 0.4


def test_webrtc_vad_detection():
    vad = WebRTCVAD(mode=2)
    if not vad.is_available():
        return

    silence = generate_silence(duration_ms=100, sample_rate=16000)
    prob_silence = vad.process_chunk(silence, 16000)
    assert prob_silence < 0.2

    speech = generate_speech_like_signal(duration_ms=100, sample_rate=16000, amplitude=0.7)
    prob_speech = vad.process_chunk(speech, 16000)
    assert prob_speech > 0.5


def test_silero_vad_detection():
    vad = SileroVAD()
    if not vad.is_available():
        return

    # Process silence
    vad.reset()
    silence = generate_silence(duration_ms=100, sample_rate=16000)
    prob_silence = vad.process_chunk(silence, 16000)
    assert prob_silence < 0.2

    # Process real speech audio fixture
    sample_file = Path(__file__).parent.parent / "fixtures" / "en_example.wav"
    if sample_file.exists():
        data, sr = sf.read(str(sample_file), dtype="int16")
        normalizer = AudioNormalizer()
        pcm16 = normalizer.normalize(data.tobytes(), source_sample_rate=sr)

        vad.reset()
        probs = []
        for i in range(16000, 32000, 1600):  # test 1 second of speech
            chunk = pcm16[i:i+1600]
            p = vad.process_chunk(chunk, 16000)
            probs.append(p)
        assert max(probs) > 0.5
