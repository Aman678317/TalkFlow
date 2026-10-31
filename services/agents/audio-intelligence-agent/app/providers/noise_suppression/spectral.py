"""Streaming spectral subtraction and Wiener filtering noise suppressor."""
from __future__ import annotations

import numpy as np
from app.providers.noise_suppression.base import BaseNoiseSuppressor


class SpectralNoiseSuppressor(BaseNoiseSuppressor):
    """Real-time streaming spectral subtraction and Wiener filter.
    
    Preserves natural speech characteristics and avoids cutting quiet syllables by using
    adaptive noise power spectral density (PSD) tracking and spectral flooring.
    """

    def __init__(
        self,
        alpha: float = 0.92,
        over_subtraction: float = 1.3,
        spectral_floor: float = 0.08,
    ):
        self.alpha = alpha
        self.over_subtraction = over_subtraction
        self.spectral_floor = spectral_floor
        self._noise_psd: np.ndarray | None = None
        self._init_frames_count = 0
        self._required_init_frames = 6

    @property
    def name(self) -> str:
        return "spectral"

    def is_available(self) -> bool:
        return True

    def reset(self) -> None:
        self._noise_psd = None
        self._init_frames_count = 0

    def process_frame(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 16000,
        is_speech: bool = False,
    ) -> bytes:
        if not pcm_bytes:
            return b""

        # Convert to float32
        x = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        n_samples = len(x)
        if n_samples == 0:
            return b""

        # Hann window
        window = np.hanning(n_samples)
        x_windowed = x * window

        # Compute real FFT
        fft_complex = np.fft.rfft(x_windowed)
        magnitude = np.abs(fft_complex)
        phase = np.angle(fft_complex)
        psd = magnitude**2

        # Initialize or update noise spectrum during non-speech
        if self._noise_psd is None or self._noise_psd.shape != psd.shape:
            self._noise_psd = psd.copy()
            self._init_frames_count = 1
        elif not is_speech or self._init_frames_count < self._required_init_frames:
            # Recursive smoothing on noise spectrum
            self._noise_psd = self.alpha * self._noise_psd + (1.0 - self.alpha) * psd
            self._init_frames_count += 1

        # Calculate Wiener attenuation gain per frequency bin
        # Gain G(f) = max(floor, PSD_clean / (PSD_clean + oversub * PSD_noise))
        noise_term = self.over_subtraction * self._noise_psd
        snr_post = psd / (noise_term + 1e-10)
        gain = snr_post / (snr_post + 1.0)
        gain = np.clip(gain, self.spectral_floor, 1.0)

        # Apply gain to magnitude, reconstruct with original phase
        cleaned_magnitude = magnitude * gain
        cleaned_complex = cleaned_magnitude * np.exp(1j * phase)

        # Inverse FFT
        cleaned_time = np.fft.irfft(cleaned_complex, n=n_samples)

        # Compensate for Hann window amplitude drop
        cleaned_time = cleaned_time * 1.5

        # Clip and convert back to PCM16
        clipped = np.clip(cleaned_time, -1.0, 1.0)
        return (clipped * 32767.0).astype(np.int16).tobytes()

