"""Benchmark manager, Real-Time Factor (RTF) engine, and processing time estimator."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class BenchmarkEngine:
    """Calculates RTF and predicts execution latency based on historical empirical benchmarks."""

    # Baseline empirical benchmarks (milliseconds of processing per second of speech)
    # Calibrated on warm RAM Ollama & Edge Neural TTS
    EMPIRICAL_RATES_MS_PER_AUDIO_SEC = {
        "agent_01_audio": 45.0,    # Audio intelligence & VAD
        "agent_02_stt": 220.0,     # Multilingual Whisper STT
        "agent_03_lid": 25.0,      # FastText LID
        "agent_04_mt": 180.0,      # Neural MT per target language
        "agent_05_qa": 65.0,       # Translation QA evaluation per target
        "agent_06_tts": 240.0,     # Edge Neural TTS per target language
        "agent_07_delivery": 10.0, # Jitter buffering & delivery packaging
    }

    @staticmethod
    def calculate_rtf(wall_clock_sec: float, audio_duration_sec: float) -> float:
        """Calculate Real-Time Factor: wall_clock_time / audio_duration."""
        if audio_duration_sec <= 0:
            return 0.0
        return round(wall_clock_sec / audio_duration_sec, 3)

    @staticmethod
    def estimate_job(
        audio_duration_sec: float,
        target_languages: List[str],
        parallel_languages: bool = True
    ) -> Dict[str, Any]:
        """Estimate processing time and RTF for a full recording before execution begins.
        
        Args:
            audio_duration_sec: Length of audio recording in seconds.
            target_languages: List of requested target languages.
            parallel_languages: Whether target languages execute concurrently.
        """
        rates = BenchmarkEngine.EMPIRICAL_RATES_MS_PER_AUDIO_SEC
        
        # Source pipeline execution time (Agents 01 -> 02 -> 03 -> 04)
        t_src_ms = (rates["agent_01_audio"] + rates["agent_02_stt"] + rates["agent_03_lid"] + rates["agent_04_mt"]) * audio_duration_sec
        
        # Per-language downstream execution time (Agents 05 -> 06 -> 07)
        t_per_lang_downstream_ms = (rates["agent_05_qa"] + rates["agent_06_tts"] + rates["agent_07_delivery"]) * audio_duration_sec
        
        if parallel_languages:
            # Parallel execution takes the duration of the single longest branch (bounded by concurrency factor)
            concurrency_factor = 1.15  # Slight lock/thread contention overhead
            t_downstream_ms = t_per_lang_downstream_ms * concurrency_factor
        else:
            t_downstream_ms = t_per_lang_downstream_ms * len(target_languages)

        total_estimated_ms = t_src_ms + t_downstream_ms
        total_estimated_sec = round(total_estimated_ms / 1000.0, 2)
        estimated_rtf = BenchmarkEngine.calculate_rtf(total_estimated_sec, audio_duration_sec)

        return {
            "audio_duration_sec": audio_duration_sec,
            "target_languages_count": len(target_languages),
            "estimated_wall_clock_sec": total_estimated_sec,
            "estimated_rtf": estimated_rtf,
            "parallel_processing": parallel_languages,
            "speed_multiplier": f"{1.0/estimated_rtf:.1f}x" if estimated_rtf > 0 else "N/A"
        }

