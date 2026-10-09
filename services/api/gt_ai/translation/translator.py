"""Translation Adapter Interface & Indic-Focused Translator (Phase 4).

Implements the Phase 4 translation adapter contract:
interface Translator {
  translate(input: {
    text: string,
    sourceLanguage: string,
    targetLanguage: string,
    context?: string,
  }): Promise<{
    text: string,
    detectedSourceLanguage?: string,
  }>
}

Features:
- Strong Indic-language support (Hindi, Marathi, Bengali, Tamil, Telugu, Gujarati,
  Kannada, Malayalam, Punjabi, Urdu) with direct native translation
- Open-source / self-hosted adapter ready (CTranslate2 NLLB, Madlad400, or Neural router)
- Context-aware translation: accepts previous segment context, strictly capped to 250 chars
- Natural conversational phrasing (avoids literal word-by-word artifacts)
- TTS-friendly punctuation and sentence boundary normalization
- Strict data privacy: no external leaks of private call content
"""
from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from gt_ai.base import TranslationProvider
from gt_ai.types import Intent, TranslationRequest, TranslationResult

log = logging.getLogger("gt_ai.translation.translator")

MAX_CONTEXT_CHARS = 250

INDIC_LANGUAGES = {
    "hi": "Hindi",
    "mr": "Marathi",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "gu": "Gujarati",
    "kn": "Kannada",
    "ml": "Malayalam",
    "pa": "Punjabi",
    "ur": "Urdu",
    "or": "Odia",
    "as": "Assamese",
}


@dataclass(slots=True)
class TranslationResponse:
    text: str
    detected_source_language: str | None = None
    confidence: float | None = None
    model: str = ""
    provider: str = ""
    latency_ms: float = 0.0

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


class Translator(ABC):
    """Abstract interface for translation engines."""

    @abstractmethod
    async def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
        context: str | None = None,
    ) -> TranslationResponse:
        """Translate text from source_language to target_language."""


class IndicTranslator(Translator):
    """Production translator with strong Indic-language support and TTS normalization."""

    def __init__(self, provider: TranslationProvider) -> None:
        self.provider = provider

    def _normalize_for_tts(self, text: str, target_lang: str) -> str:
        """Ensure translated text has TTS-friendly sentence boundaries and punctuation."""
        t = (text or "").strip()
        if not t:
            return ""

        # Remove repetitive punctuation artifacts (e.g. "??", "!!", "....")
        t = re.sub(r"\.{2,}", "...", t)
        t = re.sub(r"!{2,}", "!", t)
        t = re.sub(r"\?{2,}", "?", t)

        # Ensure sentence has a natural terminating boundary for TTS synthesis
        # Indic Devanagari script often uses danda '।' or standard period '.'
        if not t.endswith((".", "!", "?", "।", "؟", "۔", "…")):
            if target_lang in ("hi", "mr", "ne"):
                t += "।"
            elif target_lang == "ur":
                t += "۔"
            else:
                t += "."
        return t

    def _prepare_context(self, context: str | None) -> list[str]:
        if not context:
            return []
        cleaned = context.strip()
        if len(cleaned) > MAX_CONTEXT_CHARS:
            cleaned = cleaned[-MAX_CONTEXT_CHARS:].strip()
        return [cleaned] if cleaned else []

    async def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
        context: str | None = None,
    ) -> TranslationResponse:
        t0 = time.perf_counter()
        raw_text = (text or "").strip()
        if not raw_text:
            return TranslationResponse(
                text="",
                detected_source_language=source_language,
                latency_ms=0.0,
            )

        src = (source_language or "auto").lower()
        tgt = target_language.lower()

        # Same-language passthrough
        if src == tgt and src != "auto":
            return TranslationResponse(
                text=raw_text,
                detected_source_language=src,
                confidence=1.0,
                model="passthrough",
                provider="identity",
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        context_list = self._prepare_context(context)
        req = TranslationRequest(
            text=raw_text,
            source_lang=src,
            target_lang=tgt,
            intent=Intent.LATENCY_OPTIMIZED,
            context=context_list,
        )

        result = await self.provider.translate(req)
        normalized_output = self._normalize_for_tts(result.text, tgt)
        latency = (time.perf_counter() - t0) * 1000

        return TranslationResponse(
            text=normalized_output,
            detected_source_language=result.source_lang or src,
            confidence=result.confidence,
            model=result.model,
            provider=result.provider,
            latency_ms=latency,
        )
