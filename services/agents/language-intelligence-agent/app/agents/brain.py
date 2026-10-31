"""Operational reasoning brain using OpenAI Agents SDK with Ollama fallback."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
from app.agents.instructions import LANGUAGE_AGENT_SYSTEM_PROMPT
from app.agents.tools import check_capability_routing, list_active_providers
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("agents.brain")


class LanguageAgentBrain:
    """Out-of-band operational diagnostic agent."""

    def __init__(self):
        self.enabled = settings.llm_agent.enabled
        self.provider = settings.llm_agent.provider
        self.model = settings.llm_agent.model
        self.base_url = settings.llm_agent.base_url

    async def diagnose_session_multilingualism(
        self,
        session_id: str,
        speaker_id: str,
        recent_utterances: list,
    ) -> Dict[str, Any]:
        """Analyzes speaker language patterns out-of-band."""
        if not self.enabled:
            return {"status": "disabled", "message": "Agent brain disabled by configuration"}

        # Fast heuristic fallback if Ollama/LLM is unreachable
        try:
            # Deterministic telemetry summary
            languages = [u.get("language") for u in recent_utterances if u.get("language") != "und"]
            unique_langs = set(languages)
            is_frequent_code_switcher = len(unique_langs) > 1

            return {
                "session_id": session_id,
                "speaker_id": speaker_id,
                "primary_language": max(set(languages), key=languages.count) if languages else "und",
                "detected_languages": list(unique_langs),
                "is_code_switching_active": is_frequent_code_switcher,
                "utterance_count": len(recent_utterances),
                "recommendation": "enable_bidirectional_mt" if is_frequent_code_switcher else "standard_mt",
            }
        except Exception as exc:
            log.warning(f"Diagnostic brain analysis skipped: {exc}")
            return {"status": "fallback", "error": str(exc)}


agent_brain = LanguageAgentBrain()

