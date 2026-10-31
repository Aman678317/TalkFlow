"""Provider router registry and candidate selector."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional
from app.core.config import settings
from app.core.exceptions import UnsupportedLanguagePairError
from app.providers.base import BaseProvider, Intent, TranslationRequest, TranslationResult
from app.providers.argos.provider import ArgosProvider
from app.providers.marian.provider import MarianProvider
from app.providers.nllb.provider import NllbProvider
from app.providers.madlad400.provider import Madlad400Provider
from app.providers.online.neural_online import NeuralOnlineProvider
from app.providers.experimental.qwen_translation import QwenTranslationProvider
from app.routing.capability_registry import capability_registry
from app.routing.fallback import FallbackExecutor
from app.routing.route_policy import RoutePolicy

log = logging.getLogger("agent04.routing.router")


class ProviderRouter:
    """Manages active providers and routes requests based on capability, intent, and privacy."""

    def __init__(self) -> None:
        self.providers: Dict[str, BaseProvider] = {
            "argos": ArgosProvider(packages_dir=settings.models.argos.packages_dir),
            "marian": MarianProvider(cache_dir=settings.models.marian.cache_dir),
            "nllb": NllbProvider(
                model_dir=settings.models.nllb.model_dir,
                tokenizer_file=settings.models.nllb.tokenizer_file,
                compute_type=settings.translation.compute_type,
                device=settings.translation.device,
                license_warning_accepted=settings.models.nllb.license_warning_accepted,
            ),
            "madlad400": Madlad400Provider(
                model_id=settings.models.madlad400.model_id,
                cache_dir=settings.models.madlad400.cache_dir,
            ),
            "neural_online": NeuralOnlineProvider(deepl_key=settings.models.online.deepl_api_key),
            "local_qwen": QwenTranslationProvider(
                base_url=settings.llm_agent.base_url,
                model=settings.llm_agent.model,
            ),
        }

    def list_providers(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": p.name,
                "private": p.private,
                "quality_tier": p.quality_tier,
                "cost_tier": p.cost_tier,
                "latency_class": p.latency_class,
                "requires_gpu": p.requires_gpu,
                "ready": p.runtime_ready(),
            }
            for p in self.providers.values()
        ]

    def get_provider(self, name: str) -> Optional[BaseProvider]:
        return self.providers.get(name)

    async def route_and_translate(self, req: TranslationRequest) -> TranslationResult:
        src = req.source_lang.lower()
        tgt = req.target_lang.lower()

        # Check capability registry
        cap = capability_registry.get_pair_capability(src, tgt)
        if cap and cap.status == "UNSUPPORTED":
            raise UnsupportedLanguagePairError(f"Language pair {src}->{tgt} is marked UNSUPPORTED in capability registry.")

        candidate_names = RoutePolicy.get_candidate_providers(req.intent, req.tenant_private_only)
        return await FallbackExecutor.execute_with_fallback(self.providers, candidate_names, req)


provider_router = ProviderRouter()

