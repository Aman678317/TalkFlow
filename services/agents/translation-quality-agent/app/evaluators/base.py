"""Base evaluator interface for reference-free and reference-based metrics."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pydantic import BaseModel


class EvaluatorResult(BaseModel):
    evaluator_name: str
    metric_type: str  # reference_free | reference_based | semantic
    score: float      # Normalized 0.0 to 1.0 (or BLEU 0-100)
    details: Dict[str, Any] = {}
    is_available: bool = True
    latency_ms: float = 0.0


class BaseEvaluator(ABC):
    """Abstract base class for all translation quality evaluators."""

    name: str = "base_evaluator"

    @abstractmethod
    def evaluate(
        self,
        source: str,
        hypothesis: str,
        source_lang: str,
        target_lang: str,
        reference: Optional[str] = None,
    ) -> EvaluatorResult:
        """Executes quality evaluation and returns EvaluatorResult."""
        raise NotImplementedError

