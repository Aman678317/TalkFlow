"""langdetect language detection provider with Unicode-script heuristics."""
from __future__ import annotations

import re
from typing import Any, List, Set, Tuple
from app.core.exceptions import DetectionError
from app.core.logging import get_logger
from app.language.codes import normalize_language_code
from app.language.registry import (
    ENGLISH_WORDS,
    LanguageProfileRegistry,
    MARATHI_MARKERS_REGEX,
    HINDI_MARKERS_REGEX,
    URDU_SPECIFIC_CHARS,
)
from app.models.schemas import CandidateLanguage, DetectionResult
from app.providers.base import BaseLanguageDetector

log = get_logger("langdetect.provider")

# Script block -> likely language candidates (excluding shared Indic punctuation \u0964 and \u0965)
SCRIPT_HINTS: List[Tuple[re.Pattern, List[str]]] = [
    (re.compile(r"[\u0904-\u0939\u0958-\u0961]"), ["hi", "mr"]),   # Devanagari letters
    (re.compile(r"[\u0985-\u09B9\u09CE\u09DC-\u09DF]"), ["bn"]),   # Bengali letters
    (re.compile(r"[\u0B80-\u0BFF]"), ["ta"]),         # Tamil
    (re.compile(r"[\u0C00-\u0C7F]"), ["te"]),         # Telugu
    (re.compile(r"[\u0A80-\u0AFF]"), ["gu"]),         # Gujarati
    (re.compile(r"[\u0C80-\u0CFF]"), ["kn"]),         # Kannada
    (re.compile(r"[\u0D00-\u0D7F]"), ["ml"]),         # Malayalam
    (re.compile(r"[\u0A00-\u0A7F]"), ["pa"]),         # Punjabi / Gurmukhi
    (re.compile(r"[\u0B00-\u0B7F]"), ["or"]),         # Odia
    (re.compile(r"[\u0600-\u06FF]"), ["ur", "ar"]),   # Arabic / Urdu
    (re.compile(r"[\u3040-\u30FF]"), ["ja"]),         # Japanese Kana
    (re.compile(r"[\u4E00-\u9FFF]"), ["zh"]),         # Chinese Hanzi
    (re.compile(r"[\uAC00-\uD7AF]"), ["ko"]),         # Korean Hangul
    (re.compile(r"[\u0400-\u04FF]"), ["ru"]),         # Russian Cyrillic
]


class LangDetectProvider(BaseLanguageDetector):
    """Statistical detector combined with Unicode script heuristics and Indic disambiguation."""

    @property
    def name(self) -> str:
        return "langdetect"

    @property
    def model_name(self) -> str:
        return "langdetect-indic-heuristics"

    def healthy(self) -> bool:
        try:
            import langdetect  # noqa: F401
            return True
        except ImportError:
            return False

    def is_available(self) -> bool:
        return self.healthy()

    def supported_languages(self) -> Set[str]:
        return {
            "en", "hi", "mr", "bn", "ta", "te", "gu", "kn", "ml", "pa", "ur",
            "or", "ar", "ja", "zh", "ko", "ru", "es", "fr", "de", "pt", "it",
            "nl", "id", "vi", "th", "tr", "pl", "sv", "da", "fi", "no", "el", "he"
        }

    def detect(self, text: str, top_k: int = 5, **kwargs: Any) -> DetectionResult:
        clean_text = text.strip()
        if not clean_text:
            return DetectionResult(language="und", confidence=0.0, provider=self.name)

        # 1. Non-Latin Unicode Script Heuristics (High accuracy for Indic/CJK/Arabic)
        for rx, langs in SCRIPT_HINTS:
            if rx.search(clean_text):
                if len(langs) == 1:
                    return DetectionResult(
                        language=langs[0],
                        confidence=0.96,
                        provider=self.name,
                        alternatives=[],
                    )

                # Devanagari Hindi vs. Marathi Disambiguation
                if langs == ["hi", "mr"]:
                    lang, conf = LanguageProfileRegistry.disambiguate_devanagari(clean_text)
                    alt_lang = "mr" if lang == "hi" else "hi"
                    return DetectionResult(
                        language=lang,
                        confidence=conf,
                        provider=self.name,
                        alternatives=[CandidateLanguage(language=alt_lang, confidence=0.50, provider=self.name)],
                    )

                # Urdu vs. Arabic Disambiguation
                if langs == ["ur", "ar"]:
                    lang, conf = LanguageProfileRegistry.disambiguate_arabic_script(clean_text)
                    alt_lang = "ar" if lang == "ur" else "ur"
                    return DetectionResult(
                        language=lang,
                        confidence=conf,
                        provider=self.name,
                        alternatives=[CandidateLanguage(language=alt_lang, confidence=0.45, provider=self.name)],
                    )

        # 2. Latin-script function word heuristics (prevents short-text false classifications)
        tokens = [w.lower() for w in re.findall(r"\b[a-zA-Záéíóúüñßäöüàâçèêëîïôûùÿ']+\b", clean_text)]
        if tokens:
            en_matches = sum(1 for t in tokens if t in ENGLISH_WORDS)
            if en_matches >= 2 or (len(tokens) <= 3 and en_matches >= 1):
                conf = min(0.99, 0.70 + (en_matches / len(tokens)) * 0.3)
                return DetectionResult(
                    language="en",
                    confidence=round(conf, 4),
                    provider=self.name,
                    alternatives=[],
                )

        # 3. Statistical language-detection fallback
        try:
            from langdetect import detect_langs, DetectorFactory
            DetectorFactory.seed = 0
            res = detect_langs(clean_text)
            top = res[0]
            canonical = normalize_language_code(top.lang)
            alts = [
                CandidateLanguage(
                    language=normalize_language_code(r.lang),
                    confidence=round(float(r.prob), 4),
                    provider=self.name,
                )
                for r in res[1:4]
                if normalize_language_code(r.lang) != canonical
            ]
            return DetectionResult(
                language=canonical,
                confidence=round(float(top.prob), 4),
                provider=self.name,
                alternatives=alts,
            )
        except Exception:
            return DetectionResult(language="und", confidence=0.30, provider=self.name)
