"""Modular adapter hook for COMET / COMETKiwi / XCOMET."""
from __future__ import annotations

import time
from typing import Optional
from app.evaluators.base import BaseEvaluator, EvaluatorResult


class CometAdapterEvaluator(BaseEvaluator):
    """Adapter hook for unbabel-comet (COMET-22, COMETKiwi, XCOMET).
    
    TalkFlow specification: When unbabel-comet is not installed or GPU weights
    are unavailable, report honest degradation; never fabricate quality scores.
    """

    name = "comet"

    def __init__(self, model_name: str = "Unbabel/wmt22-comet-da"):
        self.model_name = model_name
        self._model = None
        self._load_attempted = False

    def _try_load(self) -> bool:
        if self._load_attempted:
            return self._model is not None
        self._load_attempted = True
        try:
            import comet
            # In production, models are pre-cached in local weights cache
            self._model = comet.load_from_checkpoint(comet.download_model(self.model_name))
            return True
        except Exception:
            self._model = None
            return False

    def evaluate(
        self,
        source: str,
        hypothesis: str,
        source_lang: str,
        target_lang: str,
        reference: Optional[str] = None,
    ) -> EvaluatorResult:
        started = time.perf_counter()
        loaded = self._try_load()

        if not loaded:
            return EvaluatorResult(
                evaluator_name=self.name,
                metric_type="neural_comet",
                score=0.0,
                details={
                    "status": "NOT_CONFIGURED",
                    "reason": "unbabel-comet optional neural package not installed or GPU weights not cached locally.",
                    "license": "CC-BY-NC-SA-4.0",
                },
                is_available=False,
                latency_ms=0.0,
            )

        try:
            data = [{"src": source, "mt": hypothesis, "ref": reference or ""}]
            model_output = self._model.predict(data, batch_size=1, gpus=0)
            score = float(model_output.scores[0])
            latency = round((time.perf_counter() - started) * 1000, 2)
            return EvaluatorResult(
                evaluator_name=self.name,
                metric_type="neural_comet",
                score=round(score, 3),
                details={"model": self.model_name, "raw_score": score},
                is_available=True,
                latency_ms=latency,
            )
        except Exception as exc:
            return EvaluatorResult(
                evaluator_name=self.name,
                metric_type="neural_comet",
                score=0.0,
                details={"status": "ERROR", "error": str(exc)},
                is_available=False,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            )

