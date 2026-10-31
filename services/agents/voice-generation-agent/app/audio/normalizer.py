"""Audio normalizer and signal processing for Agent 06."""
from __future__ import annotations

import io
import wave
from typing import Optional, Tuple
import numpy as np


class AudioNormalizer:
    """Normalizes sample rates, formats, channels, and amplitudes for TalkFlow TTS."""

    def __init__(
        self,
        default_sample_rate: int = 24000,
        target_peak_dbfs: float = -1.0,
    ) -> None:
        self.default_sample_rate = default_sample_rate
        self.target_peak = 10.0 ** (target_peak_dbfs / 20.0)

    def normalize_pcm(
        self,
        pcm_bytes: bytes,
        source_sr: int,
        target_sr: Optional[int] = None,
        channels: int = 1,
    ) -> Tuple[bytes, int]:
        """Normalize raw PCM16 bytes: mono downmix, sample rate conversion, peak scaling."""
        if not pcm_bytes:
            return b"", target_sr or self.default_sample_rate

        dst_sr = target_sr or self.default_sample_rate
        audio = np.frombuffer(pcm_bytes, dtype=np.int16)

        # Downmix to mono if stereo
        if channels == 2:
            audio = audio.reshape(-1, 2).mean(axis=1).astype(np.int16)

        # Resample if sample rate doesn't match
        if source_sr != dst_sr:
            from scipy import signal
            num_samples = int(len(audio) * float(dst_sr) / source_sr)
            resampled = signal.resample(audio.astype(np.float32), num_samples)
            audio = np.clip(resampled, -32768, 32767).astype(np.int16)

        # Peak normalization if non-silent
        float_audio = audio.astype(np.float32) / 32768.0
        max_peak = np.max(np.abs(float_audio))
        if max_peak > 1e-4:
            scale = min(self.target_peak / max_peak, 2.0)  # max 6dB boost
            float_audio = np.clip(float_audio * scale, -1.0, 1.0)
            audio = (float_audio * 32767.0).astype(np.int16)

        return audio.tobytes(), dst_sr

    def pcm_to_wav(self, pcm_bytes: bytes, sample_rate: int = 24000) -> bytes:
        """Wrap raw PCM16 bytes into a standard RIFF/WAV header."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        return buf.getvalue()

    def wav_to_pcm(self, wav_bytes: bytes) -> Tuple[bytes, int, int]:
        """Extract PCM frames, sample rate, and channels from a WAV buffer."""
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            sr = wf.getframerate()
            ch = wf.getnchannels()
            frames = wf.readframes(wf.getnframes())
        return frames, sr, ch

