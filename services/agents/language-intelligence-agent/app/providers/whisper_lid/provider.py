"""Whisper Audio Language Identification provider for Agent 03."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Set
from app.core.logging import get_logger
from app.language.codes import LanguageCodes, normalize_language_code
from app.models.schemas import CandidateLanguage, DetectionResult
from app.providers.base import BaseLanguageDetector

log = get_logger("providers.whisper_lid")


class WhisperLIDProvider(BaseLanguageDetector):
    """Audio-based language identification provider extracting signals from Whisper STT."""

    def __init__(self, model_size: str = "base"):
        self._model_size = model_size
        self._available = True

    @property
    def name(self) -> str:
        return "whisper-lid"

    @property
    def model_name(self) -> str:
        return f"whisper-{self._model_size}-lid"

    def healthy(self) -> bool:
        return self._available

    def is_available(self) -> bool:
        return self._available

    def supported_languages(self) -> Set[str]:
        return {
            "en", "hi", "mr", "bn", "ta", "te", "gu", "ur", "kn", "ml", "pa",
            "es", "fr", "de", "zh", "ja", "ar", "ru", "pt", "it", "nl", "ko",
        }

    def detect(self, text: str, top_k: int = 5, **kwargs: Any) -> DetectionResult:
        """Text detection fallback when called via standard interface.
        Extracts language hint if provided in kwargs.
        """
        hint = kwargs.get("language_hint") or kwargs.get("audio_lid")
        hint_prob = float(kwargs.get("hint_probability", 0.85))

        if hint:
            norm_code = normalize_language_code(hint)
            return DetectionResult(
                language=norm_code,
                confidence=min(1.0, max(0.0, hint_prob)),
                provider=self.name,
                alternatives=[CandidateLanguage(language=norm_code, confidence=hint_prob, provider=self.name)],
            )

        return DetectionResult(
            language="und",
            confidence=0.0,
            provider=self.name,
            alternatives=[],
        )

    def extract_from_stt_event(self, event_meta: Dict[str, Any]) -> Optional[DetectionResult]:
        """Extracts Whisper LID probabilities and hints from Agent 02 transcript event metadata."""
        hint = event_meta.get("language") or event_meta.get("language_hint")
        if not hint or hint.lower() in ("auto", "none", "und"):
            return None

        prob = float(event_meta.get("language_probability", 0.80))
        norm_code = normalize_language_code(hint)

        alternatives = []
        raw_candidates = event_meta.get("language_candidates", [])
        for c in raw_candidates:
            if isinstance(c, dict) and "language" in c:
                c_code = normalize_language_code(c["language"])
                if c_code != norm_code:
                    alternatives.append(CandidateLanguage(
                        language=c_code,
                        confidence=float(c.get("probability", 0.0)),
                        provider=self.name,
                    ))

        return DetectionResult(
            language=norm_code,
            confidence=prob,
            provider=self.name,
            alternatives=alternatives[:5],
        )
