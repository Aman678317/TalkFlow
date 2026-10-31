"""Audio quality analysis and metrics computation module."""
from __future__ import annotations

import math
from typing import List, Tuple
import numpy as np
from app.models.schemas import AudioQualityMetrics


class AudioQualityAnalyzer:
    """Computes acoustic indicators: RMS, Peak, SNR, clipping, silence ratio, and quality status."""

    def __init__(
        self,
        snr_warning_threshold_db: float = 10.0,
        clipping_warning_ratio: float = 0.01,
        silence_warning_ratio: float = 0.95,
        min_confidence_good: float = 0.75,
        min_confidence_fair: float = 0.50,
    ):
        self.snr_warning_threshold_db = snr_warning_threshold_db
        self.clipping_warning_ratio = clipping_warning_ratio
        self.silence_warning_ratio = silence_warning_ratio
        self.min_confidence_good = min_confidence_good
        self.min_confidence_fair = min_confidence_fair

    def analyze(
        self,
        pcm_bytes: bytes,
        speech_duration_ms: int = 0,
        estimated_noise_floor_rms: float | None = None,
        sample_rate: int = 16000,
    ) -> AudioQualityMetrics:
        """Evaluates PCM16 bytes and produces structured AudioQualityMetrics."""
        if not pcm_bytes:
            return AudioQualityMetrics(
                rms=0.0,
                peak=0.0,
                snr_db=0.0,
                clipping_ratio=0.0,
                silence_ratio=1.0,
                speech_duration_ms=0,
                noise_level_db=-96.0,
                confidence=0.0,
                quality_status="poor",
                issues=["empty_audio"],
            )

        samples = np.frombuffer(pcm_bytes, dtype=np.int16)
        total_samples = len(samples)
        if total_samples == 0:
            return AudioQualityMetrics(
                rms=0.0,
                peak=0.0,
                snr_db=0.0,
                clipping_ratio=0.0,
                silence_ratio=1.0,
                speech_duration_ms=0,
                noise_level_db=-96.0,
                confidence=0.0,
                quality_status="poor",
                issues=["zero_samples"],
            )

        float_samples = samples.astype(np.float32) / 32768.0

        # 1. Peak & RMS
        peak = float(np.max(np.abs(float_samples)))
        rms = float(np.sqrt(np.mean(float_samples**2)) + 1e-10)

        # 2. Clipping detection (values reaching +/- 32760 / 32768)
        clipped_count = int(np.sum(np.abs(samples) >= 32760))
        clipping_ratio = float(clipped_count / total_samples)

        # 3. Silence / low energy frame analysis (per 20ms block)
        block_size = int(sample_rate * 0.02)
        if block_size > 0 and total_samples >= block_size:
            num_blocks = total_samples // block_size
            blocks = float_samples[:num_blocks * block_size].reshape(num_blocks, block_size)
            block_rms = np.sqrt(np.mean(blocks**2, axis=1))
            silence_blocks = np.sum(block_rms < 0.01)  # -40 dBFS
            silence_ratio = float(silence_blocks / num_blocks)
            noise_floor_rms = float(np.percentile(block_rms, 10))
        else:
            silence_ratio = 1.0 if rms < 0.01 else 0.0
            noise_floor_rms = rms * 0.5

        if estimated_noise_floor_rms is not None and estimated_noise_floor_rms > 0:
            noise_floor_rms = min(noise_floor_rms, estimated_noise_floor_rms)

        # 4. SNR estimation
        noise_floor_rms = max(noise_floor_rms, 1e-5)
        snr_linear = rms / noise_floor_rms
        snr_db = float(max(-20.0, min(60.0, 20.0 * math.log10(max(1.0, snr_linear)))))
        noise_level_db = float(20.0 * math.log10(noise_floor_rms))

        # 5. Determine issues and status
        issues: List[str] = []
        if clipping_ratio > self.clipping_warning_ratio:
            issues.append(f"clipping_detected: {clipping_ratio * 100:.1f}%")
        if snr_db < self.snr_warning_threshold_db:
            issues.append(f"low_snr: {snr_db:.1f}dB")
        if rms < 0.01:
            issues.append("low_volume_speech")
        if silence_ratio > self.silence_warning_ratio and speech_duration_ms > 0:
            issues.append("excessive_silence")

        # 6. Overall Confidence & Quality Status
        confidence, status = self._compute_confidence(
            rms=rms,
            snr_db=snr_db,
            clipping_ratio=clipping_ratio,
            silence_ratio=silence_ratio,
        )

        return AudioQualityMetrics(
            rms=round(rms, 4),
            peak=round(peak, 4),
            snr_db=round(snr_db, 2),
            clipping_ratio=round(clipping_ratio, 4),
            silence_ratio=round(silence_ratio, 4),
            speech_duration_ms=speech_duration_ms,
            noise_level_db=round(noise_level_db, 2),
            confidence=round(confidence, 3),
            quality_status=status,
            issues=issues,
        )

    def _compute_confidence(
        self,
        rms: float,
        snr_db: float,
        clipping_ratio: float,
        silence_ratio: float,
    ) -> Tuple[float, str]:
        """Calculates normalized confidence score and categorized status."""
        score = 1.0

        # Clipping penalties
        if clipping_ratio > 0.05:
            score -= 0.4
        elif clipping_ratio > 0.01:
            score -= 0.2

        # SNR penalties
        if snr_db < 5.0:
            score -= 0.4
        elif snr_db < 12.0:
            score -= 0.2
        elif snr_db > 20.0:
            score += 0.05

        # Volume penalties
        if rms < 0.005:  # Extremely quiet
            score -= 0.3
        elif rms < 0.02:
            score -= 0.1

        confidence = max(0.0, min(1.0, score))

        if confidence >= self.min_confidence_good and not clipping_ratio > 0.02:
            status = "good"
        elif confidence >= self.min_confidence_fair:
            status = "fair"
        else:
            status = "poor"

        return confidence, status

