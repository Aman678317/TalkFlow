"""Provider failover orchestrator for resilient translation execution."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional
from app.providers.base import BaseProvider, TranslationRequest, TranslationResult
from app.core.exceptions import ProviderUnavailableError

log = logging.getLogger("agent04.routing.fallback")


class FallbackExecutor:
    """Executes translation attempts across candidate providers until success or exhaustion."""

    @staticmethod
    async def execute_with_fallback(
        providers: Dict[str, BaseProvider],
        candidate_names: List[str],
        req: TranslationRequest,
    ) -> TranslationResult:
        errors = []

        for name in candidate_names:
            provider = providers.get(name)
            if not provider:
                continue

            if not provider.runtime_ready():
                log.debug(f"Candidate {name} failed runtime_ready() pre-flight gate. Skipping.")
                continue

            try:
                log.info(f"Attempting translation {req.source_lang}->{req.target_lang} via {name}...")
                result = await provider.translate(req)
                return result
            except Exception as e:
                log.warning(f"Provider {name} failed: {e}. Trying next candidate...")
                errors.append(f"{name}: {e}")

        all_errs = "; ".join(errors) if errors else "No eligible providers found"
        raise ProviderUnavailableError(f"All translation provider candidates failed for {req.source_lang}->{req.target_lang}: {all_errs}")

