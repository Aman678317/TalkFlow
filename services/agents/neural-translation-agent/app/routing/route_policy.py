"""Route policy matching intent, privacy rules, and capability gates."""
from __future__ import annotations

from typing import List
from app.providers.base import Intent


class RoutePolicy:
    """Calculates ordered provider priority for a translation request."""

    @staticmethod
    def get_candidate_providers(intent: Intent, tenant_private_only: bool) -> List[str]:
        """Returns ordered candidate provider names based on policy constraints."""
        if tenant_private_only or intent == Intent.PRIVATE_ONLY or intent == Intent.OFFLINE_ONLY:
            # Strictly private / offline local inference paths only
            return ["argos", "marian", "nllb", "local_qwen"]

        if intent == Intent.LATENCY_OPTIMIZED:
            return ["neural_online", "argos", "marian", "nllb"]

        if intent == Intent.QUALITY_OPTIMIZED:
            return ["neural_online", "madlad400", "marian", "nllb", "argos"]

        if intent == Intent.COST_OPTIMIZED:
            return ["argos", "marian", "nllb", "neural_online"]

        # Default fallback chain
        return ["neural_online", "argos", "marian", "nllb", "local_qwen"]

