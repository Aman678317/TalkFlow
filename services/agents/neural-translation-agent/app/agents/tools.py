"""Structured diagnostic tools for the OpenAI Agents SDK."""
from __future__ import annotations

import json
from typing import Any, Dict, List
from agents import function_tool
from app.core.config import settings
from app.routing.capability_registry import capability_registry
from app.routing.provider_router import provider_router
from app.monitoring.latency import latency_tracker


def get_translation_status_fn() -> str:
    """Returns general service health, uptime, and primary provider status."""
    return json.dumps({
        "status": "online",
        "primary_provider": settings.translation.primary_provider,
        "default_intent": settings.routing.default_intent,
        "zero_pivot_enforced": not settings.routing.allow_pivot_translation,
        "active_providers_count": len(provider_router.providers),
    }, indent=2)


def list_translation_providers_fn() -> str:
    """Lists available translation provider adapters and their runtime readiness."""
    providers = provider_router.list_providers()
    return json.dumps(providers, indent=2)


def get_supported_language_pairs_fn() -> str:
    """Lists evaluated language pairs, their production status, and BLEU benchmarks."""
    caps = capability_registry.list_capabilities()
    data = [c.model_dump() for c in caps]
    return json.dumps(data, indent=2)


def compare_language_pair_providers_fn(source_lang: str, target_lang: str) -> str:
    """Compares potential providers and recommendations for a specific language pair."""
    src = source_lang.lower()
    tgt = target_lang.lower()
    cap = capability_registry.get_pair_capability(src, tgt)
    status = cap.status if cap else "UNSUPPORTED"
    rec = cap.preferred_provider if cap else "none"
    return json.dumps({
        "source_lang": src,
        "target_lang": tgt,
        "status": status,
        "recommended_provider": rec,
        "direct_supported": cap.direct if cap else False,
    }, indent=2)


def get_latency_stats_fn(source_lang: str, target_lang: str) -> str:
    """Returns latency percentiles (p50, p95, p99) for a language pair."""
    stats = latency_tracker.get_stats(source_lang, target_lang)
    return json.dumps(stats, indent=2)


def lookup_translation_memory_fn(source_text: str, source_lang: str, target_lang: str) -> str:
    """Checks TalkFlow Translation Memory for approved human or verified translations."""
    from rag.memory.translation_memory import TranslationMemoryManager
    tm = TranslationMemoryManager()
    entry = tm.lookup(source_text, source_lang, target_lang)
    if entry:
        return json.dumps({
            "found": True,
            "target_text": entry.target_text,
            "quality_score": entry.quality_score,
            "user_approved": entry.user_approved,
            "domain": entry.domain
        }, indent=2)
    return json.dumps({"found": False, "target_text": None}, indent=2)


def research_translation_models_fn(query: str) -> str:
    """Researches multilingual NMT models, Indian language pairs, and glossaries via RAG."""
    from rag.research.engine import AutonomousResearchEngine
    engine = AutonomousResearchEngine()
    note = engine.run_research(agent_id="agent_04", task_description=query)
    return json.dumps({
        "finding": note.synthesized_finding,
        "citations": note.citations,
        "verified": note.verified
    }, indent=2)


# Wrap with OpenAI Agents SDK function_tool
get_translation_status_tool = function_tool(get_translation_status_fn)
list_translation_providers_tool = function_tool(list_translation_providers_fn)
get_supported_language_pairs_tool = function_tool(get_supported_language_pairs_fn)
compare_language_pair_providers_tool = function_tool(compare_language_pair_providers_fn)
get_latency_stats_tool = function_tool(get_latency_stats_fn)
lookup_translation_memory_tool = function_tool(lookup_translation_memory_fn)
research_translation_models_tool = function_tool(research_translation_models_fn)

ALL_MT_TOOLS = [
    get_translation_status_tool,
    list_translation_providers_tool,
    get_supported_language_pairs_tool,
    compare_language_pair_providers_tool,
    get_latency_stats_tool,
    lookup_translation_memory_tool,
    research_translation_models_tool,
]

