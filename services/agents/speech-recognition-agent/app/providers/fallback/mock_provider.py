"""Deterministic mock STT provider for unit testing and offline fallback."""
from __future__ import annotations

import time
from typing import Optional, Set, Tuple
from app.models.schemas import STTResult, SegmentTiming, WordTimestamp
from app.providers.base import STTProvider


class MockSTTProvider(STTProvider):
    """Deterministic mock provider for offline tests and development."""

    def __init__(self, name: str = "mock-stt", default_text: str = "Test speech transcription"):
        self._name = name
        self._default_text = default_text

    @property
    def name(self) -> str:
        return self._name

    @property
    def model_name(self) -> str:
        return "mock-model-v1"

    def is_available(self) -> bool:
        return True

    def is_healthy(self) -> bool:
        return True

    def supported_languages(self) -> Set[str]:
        return {"en", "hi", "mr", "es", "fr", "de", "zh"}

    def transcribe(
        self,
        audio_pcm16: bytes,
        sample_rate: int = 16000,
        *,
        language_hint: Optional[str] = None,
        word_timestamps: bool = True,
    ) -> STTResult:
        if not audio_pcm16 or len(audio_pcm16) < 1600:
            return STTResult(
                text="",
                language=language_hint or "en",
                provider=self.name,
                model=self.model_name,
                duration_ms=0.0,
            )

        words = self._default_text.split()
        word_list = []
        dur_per_word = 0.3
        for i, w in enumerate(words):
            word_list.append(
                WordTimestamp(
                    word=w,
                    start=round(i * dur_per_word, 3),
                    end=round((i + 1) * dur_per_word, 3),
                    confidence=0.98,
                )
            )

        segment = SegmentTiming(
            start_ms=0,
            end_ms=int(len(words) * dur_per_word * 1000),
            text=self._default_text,
            words=word_list if word_timestamps else [],
        )

        return STTResult(
            text=self._default_text,
            language=language_hint or "en",
            language_probability=0.98,
            confidence=0.95,
            provider=self.name,
            model=self.model_name,
            duration_ms=5.0,
            segments=[segment],
            words=word_list if word_timestamps else [],
            no_speech_prob=0.01,
            avg_logprob=-0.15,
        )

    def detect_language(self, audio_pcm16: bytes, sample_rate: int = 16000) -> Tuple[str, float]:
        return "en", 0.99

