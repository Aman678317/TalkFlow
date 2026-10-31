"""Registry of all evaluation providers."""
from __future__ import annotations

from typing import Dict, List, Optional
from app.evaluators.base import BaseEvaluator
from app.evaluators.comet_adapter import CometAdapterEvaluator
from app.evaluators.sacrebleu_eval import SacrebleuEvaluator
from app.evaluators.semantic_eval import SemanticMultilingualEvaluator


class EvaluatorRegistry:
    """Manages and routes quality evaluation backends."""

    def __init__(self) -> None:
        self._evaluators: Dict[str, BaseEvaluator] = {
            "semantic_multilingual": SemanticMultilingualEvaluator(),
            "sacrebleu": SacrebleuEvaluator(),
            "comet": CometAdapterEvaluator(),
        }

    def get(self, name: str) -> Optional[BaseEvaluator]:
        return self._evaluators.get(name)

    def list_available(self) -> List[Dict[str, str]]:
        return [
            {"name": k, "type": v.name, "description": v.__class__.__doc__ or ""}
            for k, v in self._evaluators.items()
        ]


evaluator_registry = EvaluatorRegistry()

