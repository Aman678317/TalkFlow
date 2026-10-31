"""Code-switching tokenizer and sub-sentence span detector with exact character offsets."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from app.core.logging import get_logger
from app.detection.script_detector import ScriptDetector
from app.language.codes import normalize_language_code
from app.language.registry import (
    ENGLISH_WORDS,
    HINGLISH_WORDS,
    LanguageProfileRegistry,
)
from app.models.events import WordTiming
from app.models.schemas import LanguageSpan

log = get_logger("detection.code_switch")

# Word token regex matching words with alphanumeric and internal apostrophes/hyphens
TOKEN_REGEX = re.compile(r"([^\s\W]+(?:['\-][^\s\W]+)*)", re.UNICODE)


class CodeSwitchDetector:
    """Detects multi-language code-switching and builds continuous LanguageSpans with exact offsets."""

    @classmethod
    def detect_word_language(cls, word: str, script: str, default_deva: str = "hi", default_arab: str = "ur") -> Tuple[str, float]:
        """Classifies a single word into language and confidence based on script and vocabulary."""
        w_lower = word.lower().strip()

        # 1. Non-Latin Scripts: Directly mapped by script and lexical markers
        if script == "Deva":
            # Check Hindi vs. Marathi marker patterns for this word
            lang, conf = LanguageProfileRegistry.disambiguate_devanagari(word)
            if lang != "hi":
                return lang, conf
            return default_deva, conf

        if script == "Arab":
            lang, conf = LanguageProfileRegistry.disambiguate_arabic_script(word)
            if lang != "ur":
                return lang, conf
            return default_arab, conf

        if script == "Beng":
            return "bn", 0.98
        if script == "Taml":
            return "ta", 0.98
        if script == "Telu":
            return "te", 0.98
        if script == "Gujr":
            return "gu", 0.98
        if script == "Guru":
            return "pa", 0.98
        if script == "Knda":
            return "kn", 0.98
        if script == "Mlym":
            return "ml", 0.98
        if script == "Orya":
            return "or", 0.98
        if script == "Hani":
            return "zh", 0.95
        if script in ("Hira", "Kana"):
            return "ja", 0.95
        if script == "Hang":
            return "ko", 0.95
        if script == "Cyrl":
            return "ru", 0.95

        # 2. Latin Script: Disambiguate English vs Romanized Hindi (Hinglish) / Loanwords
        if script == "Latn":
            # Check explicit Hinglish dictionary
            if w_lower in HINGLISH_WORDS:
                return "hi", 0.92

            # Check explicit English dictionary
            if w_lower in ENGLISH_WORDS:
                return "en", 0.95

            # Morphological heuristics for Romanized Hindi / Urdu endings
            if any(w_lower.endswith(sfx) for sfx in ("enge", "ungi", "unga", "karne", "karte", "rahe", "raha", "wala", "wali")):
                return "hi", 0.85

            # Default Latin script to English with moderate confidence
            return "en", 0.70

        return "und", 0.30

    @classmethod
    def extract_language_spans(
        cls,
        text: str,
        word_timings: Optional[List[WordTiming]] = None,
        base_language: Optional[str] = None,
    ) -> List[LanguageSpan]:
        """Extracts continuous sub-sentence LanguageSpans with exact character offsets and word alignments."""
        if not text.strip():
            return []

        # Precompute sentence-level script disambiguation
        default_deva, _ = LanguageProfileRegistry.disambiguate_devanagari(text)
        default_arab, _ = LanguageProfileRegistry.disambiguate_arabic_script(text)
        if base_language in ("hi", "mr"):
            default_deva = base_language

        # Step 1: Tokenize into words with character offsets
        tokens: List[Dict[str, Any]] = []
        word_index = 0

        for match in TOKEN_REGEX.finditer(text):
            word_str = match.group(1)
            start_offset = match.start(1)
            end_offset = match.end(1)

            # Detect script of this word
            dominant_script, _ = ScriptDetector.get_dominant_script(word_str)
            lang, conf = cls.detect_word_language(
                word_str,
                dominant_script,
                default_deva=default_deva,
                default_arab=default_arab,
            )

            token_data = {
                "word": word_str,
                "start_offset": start_offset,
                "end_offset": end_offset,
                "script": dominant_script,
                "language": lang,
                "confidence": conf,
                "word_index": word_index,
                "start_ms": None,
                "end_ms": None,
            }

            # Align with Agent 02 word timings if available
            if word_timings and word_index < len(word_timings):
                wt = word_timings[word_index]
                token_data["start_ms"] = wt.start_ms
                token_data["end_ms"] = wt.end_ms

            tokens.append(token_data)
            word_index += 1

        if not tokens:
            return []

        # Step 2: Smoothing and merging adjacent tokens of same language
        spans: List[LanguageSpan] = []
        current_span_tokens: List[Dict[str, Any]] = [tokens[0]]

        for token in tokens[1:]:
            prev_token = current_span_tokens[-1]
            # Merge condition: same language and compatible script
            if token["language"] == prev_token["language"]:
                current_span_tokens.append(token)
            else:
                # Close current span and start a new one
                spans.append(cls._build_span_from_tokens(text, current_span_tokens))
                current_span_tokens = [token]

        if current_span_tokens:
            spans.append(cls._build_span_from_tokens(text, current_span_tokens))

        # Step 3: Isolated loanword absorption (if a single short 1-word token sits between same language)
        if len(spans) >= 3:
            filtered_spans: List[LanguageSpan] = []
            i = 0
            while i < len(spans):
                if 0 < i < len(spans) - 1:
                    prev_s = spans[i - 1]
                    curr_s = spans[i]
                    next_s = spans[i + 1]
                    # If prev and next have same language, and current is single word with low confidence
                    word_count = len(curr_s.text.split())
                    if prev_s.language == next_s.language and word_count == 1 and curr_s.confidence < 0.75:
                        # Absorb into surrounding language
                        absorbed_text = text[prev_s.text_start_offset:next_s.text_end_offset]
                        merged_span = LanguageSpan(
                            language=prev_s.language,
                            script=prev_s.script,
                            text=absorbed_text,
                            text_start_offset=prev_s.text_start_offset,
                            text_end_offset=next_s.text_end_offset,
                            word_start_index=prev_s.word_start_index,
                            word_end_index=next_s.word_end_index,
                            start_ms=prev_s.start_ms,
                            end_ms=next_s.end_ms,
                            confidence=round((prev_s.confidence + next_s.confidence) / 2, 4),
                            evidence_status="absorbed_loanword",
                        )
                        filtered_spans[-1] = merged_span
                        i += 2
                        continue

                filtered_spans.append(spans[i])
                i += 1
            spans = filtered_spans

        return spans

    @classmethod
    def _build_span_from_tokens(cls, full_text: str, token_group: List[Dict[str, Any]]) -> LanguageSpan:
        """Constructs a finalized LanguageSpan from grouped consecutive tokens."""
        first = token_group[0]
        last = token_group[-1]

        start_off = first["start_offset"]
        end_off = last["end_offset"]
        span_text = full_text[start_off:end_off]

        lang = first["language"]
        script = first["script"]
        avg_conf = sum(t["confidence"] for t in token_group) / len(token_group)

        start_ms = first["start_ms"]
        end_ms = last["end_ms"]

        return LanguageSpan(
            language=lang,
            script=script,
            text=span_text,
            text_start_offset=start_off,
            text_end_offset=end_off,
            word_start_index=first["word_index"],
            word_end_index=last["word_index"],
            start_ms=start_ms,
            end_ms=end_ms,
            confidence=round(avg_conf, 4),
            evidence_status="detected",
        )
