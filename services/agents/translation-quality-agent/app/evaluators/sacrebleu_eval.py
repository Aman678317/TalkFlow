"""Reference-based evaluation using SacreBLEU and chrF++."""
from __future__ import annotations

import time
from typing import Optional
from app.evaluators.base import BaseEvaluator, EvaluatorResult


class SacrebleuEvaluator(BaseEvaluator):
    name = "sacrebleu"

    def evaluate(
        self,
        source: str,
        hypothesis: str,
        source_lang: str,
        target_lang: str,
        reference: Optional[str] = None,
    ) -> EvaluatorResult:
        started = time.perf_counter()
        if not reference or not reference.strip():
            return EvaluatorResult(
                evaluator_name=self.name,
                metric_type="reference_based",
                score=0.0,
                details={"error": "Reference translation required for SacreBLEU evaluation."},
                is_available=False,
                latency_ms=0.0,
            )

        try:
            import sacrebleu

            # Sentence-level BLEU
            bleu_res = sacrebleu.sentence_bleu(hypothesis, [reference])
            bleu_score = round(bleu_res.score, 2)  # 0 to 100

            # Sentence-level chrF++ (word_order=2)
            chrf_res = sacrebleu.sentence_chrf(hypothesis, [reference], word_order=2)
            chrf_score = round(chrf_res.score, 2)  # 0 to 100

            latency = round((time.perf_counter() - started) * 1000, 2)

            # Normalized 0.0 to 1.0 composite
            norm_score = round((bleu_score * 0.5 + chrf_score * 0.5) / 100.0, 3)

            return EvaluatorResult(
                evaluator_name=self.name,
                metric_type="reference_based",
                score=norm_score,
                details={
                    "bleu": bleu_score,
                    "chrf": chrf_score,
                    "counts": bleu_res.counts,
                    "totals": bleu_res.totals,
                    "precisions": [round(p, 2) for p in bleu_res.precisions],
                    "bp": round(bleu_res.bp, 3),
                },
                is_available=True,
                latency_ms=latency,
            )

        except Exception as exc:
            # Fallback pure-python BLEU from TalkFlow canonical implementation
            from collections import Counter
            import math
            import unicodedata
            import re

            def _norm(t: str) -> str:
                t = unicodedata.normalize("NFKC", t.lower())
                return re.sub(r"\s+", " ", re.sub(r"[.,!?;:\"'()\[\]{}।؟۔]", " ", t)).strip()

            ref_words = _norm(reference).split()
            hyp_words = _norm(hypothesis).split()
            if not hyp_words or not ref_words:
                return EvaluatorResult(
                    evaluator_name=self.name,
                    metric_type="reference_based",
                    score=0.0,
                    details={"error": "Empty tokens in reference or hypothesis"},
                    is_available=True,
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                )

            precisions = []
            for n in range(1, 5):
                ref_ng = Counter(tuple(ref_words[i:i+n]) for i in range(len(ref_words) - n + 1))
                hyp_ng = Counter(tuple(hyp_words[i:i+n]) for i in range(len(hyp_words) - n + 1))
                clipped = sum(min(count, ref_ng[ng]) for ng, count in hyp_ng.items())
                total = max(1, sum(hyp_ng.values()))
                precisions.append(clipped / total)

            geo = math.exp(sum(math.log(max(1e-9, p)) for p in precisions) / len(precisions))
            bp = 1.0 if len(hyp_words) >= len(ref_words) else math.exp(1 - len(ref_words) / len(hyp_words))
            fallback_bleu = round(bp * geo * 100.0, 2)

            return EvaluatorResult(
                evaluator_name=self.name,
                metric_type="reference_based",
                score=round(fallback_bleu / 100.0, 3),
                details={"fallback_bleu": fallback_bleu, "engine": "pure_python_fallback"},
                is_available=True,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            )

