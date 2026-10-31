"""Structured tools for OpenAI Agents SDK operational STT agent."""
from __future__ import annotations

import os
from typing import Any, Dict, List
from agents import function_tool
from app.core.config import settings
from app.stt.language_hints import LanguageRegistry


def get_stt_status_fn() -> Dict[str, Any]:
    """Returns current operational status of the STT service."""
    return {
        "status": "operational",
        "agent_name": settings.agent.name,
        "version": settings.agent.version,
        "provider": settings.stt.primary_provider,
        "model_size": settings.stt.model_size,
        "device": settings.stt.device,
        "cpu_threads": settings.stt.cpu_threads,
        "compute_type": settings.stt.compute_type,
        "word_timestamps_enabled": settings.stt.word_timestamps,
        "anti_hallucination_enabled": settings.anti_hallucination.enabled,
    }


def list_stt_providers_fn() -> List[Dict[str, Any]]:
    """Lists available speech-to-text recognition providers."""
    return [
        {
            "name": "faster-whisper",
            "backend": "CTranslate2",
            "status": "active_primary",
            "precision": settings.stt.compute_type,
            "supports_code_switching": True,
        },
        {
            "name": "mock-stt",
            "backend": "deterministic_synthetic",
            "status": "fallback_ready",
            "precision": "n/a",
            "supports_code_switching": False,
        },
    ]


def list_available_models_fn() -> List[Dict[str, Any]]:
    """Lists supported model sizes with RAM/VRAM estimates and speed profiles."""
    return [
        {"model": "tiny", "params": "39M", "ram_mb": ~150, "speed": "fastest (~150ms)", "recommended_for": "ultra_low_latency"},
        {"model": "base", "params": "74M", "ram_mb": ~250, "speed": "fast (~300ms)", "recommended_for": "balanced_cpu"},
        {"model": "small", "params": "244M", "ram_mb": ~500, "speed": "moderate (~800ms)", "recommended_for": "high_accuracy_cpu"},
        {"model": "medium", "params": "769M", "ram_mb": ~1500, "speed": "heavy (~2000ms)", "recommended_for": "gpu_recommended"},
    ]


def get_language_capabilities_fn() -> List[Dict[str, Any]]:
    """Returns supported Indian and international languages."""
    return [c.model_dump() for c in LanguageRegistry.get_capabilities()]


def research_stt_knowledge_fn(query: str) -> Dict[str, Any]:
    """Researches Whisper, faster-whisper, and multilingual speech recognition using TalkFlow RAG."""
    from rag.research.engine import AutonomousResearchEngine
    engine = AutonomousResearchEngine()
    note = engine.run_research(agent_id="agent_02", task_description=query)
    return {
        "finding": note.synthesized_finding,
        "citations": note.citations,
        "verified": note.verified,
        "unresolved": note.unresolved_questions,
    }


def search_stt_docs_fn(query: str) -> List[Dict[str, Any]]:
    """Searches internal TalkFlow STT documentation and source code via hybrid RAG."""
    from rag.research.tools import ResearchTools
    from rag.models import AgentScope
    tools = ResearchTools()
    passages = tools.search_internal_knowledge(query=query, namespace=AgentScope.AGENT_02_SPEECH_RECOG, limit=4)
    return [
        {
            "title": p.title,
            "source": p.source_path_or_url,
            "content": p.content[:250],
            "citation": p.citation,
            "score": p.final_score
        }
        for p in passages
    ]


def recommend_stt_profile_fn(hardware_profile: str, primary_language: str = "en") -> Dict[str, Any]:
    """Recommends model size, compute type, and thread configuration for hardware and language."""
    hw = hardware_profile.lower()
    is_indic = primary_language in ("hi", "mr", "bn", "ta", "te", "gu", "kn", "pa", "ur")

    if "gpu" in hw or "cuda" in hw:
        return {
            "recommended_model": "small" if is_indic else "base",
            "device": "cuda",
            "compute_type": "float16",
            "cpu_threads": 4,
            "beam_size": 1,
            "expected_latency_ms": 120,
            "reasoning": "GPU detected: using float16 provides high accuracy with sub-200ms latency.",
        }
    elif "low" in hw or "2core" in hw:
        return {
            "recommended_model": "tiny",
            "device": "cpu",
            "compute_type": "int8",
            "cpu_threads": 2,
            "beam_size": 1,
            "expected_latency_ms": 250,
            "reasoning": "Low-resource CPU: tiny model guarantees real-time factor > 10x without CPU exhaustion.",
        }
    else:
        return {
            "recommended_model": "base",
            "device": "cpu",
            "compute_type": "int8",
            "cpu_threads": 4,
            "beam_size": 1,
            "expected_latency_ms": 350,
            "reasoning": "Standard CPU: base model balances English and Indian language accuracy with low CPU usage.",
        }


# Wrap as OpenAI Agents SDK FunctionTools
get_stt_status_tool = function_tool(get_stt_status_fn)
list_stt_providers_tool = function_tool(list_stt_providers_fn)
list_available_models_tool = function_tool(list_available_models_fn)
get_language_capabilities_tool = function_tool(get_language_capabilities_fn)
recommend_stt_profile_tool = function_tool(recommend_stt_profile_fn)
research_stt_knowledge_tool = function_tool(research_stt_knowledge_fn)
search_stt_docs_tool = function_tool(search_stt_docs_fn)

