"""Audio normalization, conversion, and resampling module."""
from __future__ import annotations

import math
import numpy as np
from scipy import signal


class AudioNormalizer:
    """Normalizes sample rate, channels, bit depth, and DC bias."""

    def __init__(self, target_sample_rate: int = 16000, target_channels: int = 1):
        self.target_sample_rate = target_sample_rate
        self.target_channels = target_channels

    @staticmethod
    def pcm16_to_float32(pcm_bytes: bytes) -> np.ndarray:
        """Converts raw PCM16 little-endian bytes to normalized float32 array (-1.0 to 1.0)."""
        if not pcm_bytes:
            return np.empty(0, dtype=np.float32)
        int16_arr = np.frombuffer(pcm_bytes, dtype=np.int16)
        return int16_arr.astype(np.float32) / 32768.0

    @staticmethod
    def float32_to_pcm16(float_arr: np.ndarray) -> bytes:
        """Converts float32 audio (-1.0 to 1.0) into clipped PCM16 little-endian bytes."""
        if float_arr.size == 0:
            return b""
        clipped = np.clip(float_arr, -1.0, 1.0)
        int16_arr = (clipped * 32767.0).astype(np.int16)
        return int16_arr.tobytes()

    def normalize(
        self,
        pcm_bytes: bytes,
        source_sample_rate: int = 16000,
        source_channels: int = 1,
    ) -> bytes:
        """Transforms arbitrary PCM16 audio into canonical 16kHz mono PCM16."""
        if not pcm_bytes:
            return b""

        # 1. Parse into numpy array
        int_data = np.frombuffer(pcm_bytes, dtype=np.int16)

        # 2. Convert to float32
        audio = int_data.astype(np.float32) / 32768.0

        # 3. Channel conversion (stereo to mono)
        if source_channels == 2:
            # Reshape (samples, 2) and average channels
            if len(audio) % 2 != 0:
                audio = audio[:-1]
            audio = audio.reshape(-1, 2).mean(axis=1)

        # 4. Remove DC bias (mean subtraction)
        if len(audio) > 0:
            audio = audio - np.mean(audio)

        # 5. Resample if necessary
        if source_sample_rate != self.target_sample_rate:
            gcd = math.gcd(source_sample_rate, self.target_sample_rate)
            up = self.target_sample_rate // gcd
            down = source_sample_rate // gcd
            audio = signal.resample_poly(audio, up, down).astype(np.float32)

        # 6. Convert back to canonical PCM16 bytes
        return self.float32_to_pcm16(audio)

