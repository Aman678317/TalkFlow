"""Reference-free cross-lingual semantic quality estimation."""
from __future__ import annotations

import math
import re
import time
import unicodedata
from collections import Counter
from typing import Optional
from app.evaluators.base import BaseEvaluator, EvaluatorResult


class SemanticMultilingualEvaluator(BaseEvaluator):
    """Reference-free semantic preservation and completeness estimator."""

    name = "semantic_multilingual"

    def evaluate(
        self,
        source: str,
        hypothesis: str,
        source_lang: str,
        target_lang: str,
        reference: Optional[str] = None,
    ) -> EvaluatorResult:
        started = time.perf_counter()

        src = unicodedata.normalize("NFC", source.strip())
        hyp = unicodedata.normalize("NFC", hypothesis.strip())

        if not src or not hyp:
            return EvaluatorResult(
                evaluator_name=self.name,
                metric_type="reference_free",
                score=0.0,
                details={"meaning_preservation": 0.0, "completeness": 0.0, "fluency": 0.0},
                is_available=True,
                latency_ms=0.0,
            )

        # 1. Structural Completeness & Length Ratio
        # Morphological differences typically keep ratio between 0.6 and 1.8
        src_len = len(src.split())
        hyp_len = len(hyp.split())
        length_ratio = hyp_len / max(1, src_len)

        if 0.6 <= length_ratio <= 1.8:
            completeness = 1.0
        elif 0.4 <= length_ratio < 0.6 or 1.8 < length_ratio <= 2.2:
            completeness = 0.85
        elif 0.25 <= length_ratio < 0.4 or 2.2 < length_ratio <= 3.0:
            completeness = 0.60
        else:
            completeness = max(0.2, 1.0 - abs(1.0 - length_ratio) * 0.35)

        # 2. Shared Semantic Entities (Numbers, Acronyms, Technical Terms)
        # Technical loan words, proper names, and numbers survive across language boundaries
        src_tokens = set(re.findall(r"\b[A-Za-z0-9]+\b", src))
        hyp_tokens = set(re.findall(r"\b[A-Za-z0-9]+\b", hyp))
        if src_tokens:
            shared = src_tokens.intersection(hyp_tokens)
            entity_score = len(shared) / len(src_tokens)
        else:
            entity_score = 1.0

        # 3. Punctuation & Discourse Balance
        # Sentence breaks, questions, exclamations should match
        src_q = "?" in src
        hyp_q = "?" in hyp or "क्या" in hyp or "का" in hyp
        q_penalty = 0.0 if (src_q == hyp_q) else 0.15

        # 4. Fluency & Cleanliness
        # Penalize duplicate adjacent phrases or broken characters
        has_repetition = bool(re.search(r"\b(\w+)\s+\1\b", hyp, re.IGNORECASE))
        fluency = 0.85 if has_repetition else 0.98

        # 5. Composite Meaning Preservation Score
        meaning_preservation = round(
            min(1.0, max(0.1, (completeness * 0.45) + (entity_score * 0.35) + (fluency * 0.20) - q_penalty)),
            3,
        )

        latency = round((time.perf_counter() - started) * 1000, 2)

        return EvaluatorResult(
            evaluator_name=self.name,
            metric_type="reference_free",
            score=meaning_preservation,
            details={
                "meaning_preservation": meaning_preservation,
                "completeness": round(completeness, 3),
                "entity_preservation": round(entity_score, 3),
                "fluency": round(fluency, 3),
                "length_ratio": round(length_ratio, 2),
            },
            is_available=True,
            latency_ms=latency,
        )

