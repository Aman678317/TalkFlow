"""fastText language detection provider using lid.176 model."""
from __future__ import annotations

import os
from typing import Any, List, Set, Tuple
from app.core.exceptions import DetectionError
from app.core.logging import get_logger
from app.language.codes import normalize_language_code
from app.models.schemas import CandidateLanguage, DetectionResult
from app.providers.base import BaseLanguageDetector
from app.providers.fasttext.loader import get_fasttext_model

log = get_logger("fasttext.provider")


class FastTextProvider(BaseLanguageDetector):
    """fastText 176-language classifier with direct C++ inference for NumPy 2.x compatibility."""

    def __init__(self, model_path: str = "models/lid.176.ftz", auto_download: bool = True):
        self.model_path = model_path
        self.auto_download = auto_download
        self._model = None

    @property
    def name(self) -> str:
        return "fasttext"

    @property
    def model_name(self) -> str:
        return "fasttext-lid-176"

    def healthy(self) -> bool:
        try:
            m = get_fasttext_model(self.model_path)
            return m is not None
        except Exception:
            return False

    def is_available(self) -> bool:
        return self.healthy()

    def supported_languages(self) -> Set[str]:
        return {
            "en", "hi", "mr", "bn", "ta", "te", "gu", "kn", "ml", "pa", "ur",
            "as", "or", "sa", "ne", "sd", "es", "fr", "de", "ru", "ar", "zh",
            "ja", "ko", "pt", "it", "nl", "id", "vi", "th", "tr", "pl", "sv",
        }

    def detect(self, text: str, top_k: int = 5, **kwargs: Any) -> DetectionResult:
        """Detects language using fastText model."""
        clean_text = text.replace("\n", " ").strip()
        if not clean_text:
            return DetectionResult(
                language="und",
                confidence=0.0,
                provider=self.name,
                alternatives=[],
            )

        model = get_fasttext_model(self.model_path)

        try:
            # Direct call to compiled C++ extension method to bypass NumPy 2.x np.array(copy=False) bug
            # returns list of (probability, label)
            predictions: List[Tuple[float, str]] = model.f.predict(clean_text, top_k, 0.0, "strict")

            if not predictions:
                return DetectionResult(
                    language="und",
                    confidence=0.0,
                    provider=self.name,
                    alternatives=[],
                )

            top_prob, top_label = predictions[0]
            canonical_lang = normalize_language_code(top_label)

            alternatives: List[CandidateLanguage] = []
            for prob, lbl in predictions[1:]:
                alt_lang = normalize_language_code(lbl)
                if alt_lang != canonical_lang and alt_lang != "und":
                    alternatives.append(
                        CandidateLanguage(
                            language=alt_lang,
                            confidence=round(float(prob), 4),
                            provider=self.name,
                        )
                    )

            return DetectionResult(
                language=canonical_lang,
                confidence=round(float(top_prob), 4),
                provider=self.name,
                alternatives=alternatives,
            )

        except Exception as exc:
            log.error(f"fastText detection failed: {exc}")
            raise DetectionError(f"fastText prediction error: {exc}")
