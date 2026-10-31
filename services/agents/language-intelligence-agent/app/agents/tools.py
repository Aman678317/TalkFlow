"""Operational diagnostic tools for Agent 03 reasoning brain."""
from __future__ import annotations

from typing import Any, Dict, List
from app.language.capabilities import TalkFlowCapabilityRegistry
from app.providers import get_all_providers


def check_capability_routing(language_code: str) -> Dict[str, Any]:
    """Inspects downstream translation and STT readiness for a language code."""
    return TalkFlowCapabilityRegistry.check_language_support(language_code)


def list_active_providers() -> List[Dict[str, Any]]:
    """Returns runtime health and readiness of language detection providers."""
    providers = get_all_providers()
    return [
        {
            "name": p.name,
            "model_name": p.model_name,
            "healthy": p.healthy(),
            "supported_languages_count": len(p.supported_languages()),
        }
        for p in providers
    ]

