"""OpenAI Agents SDK operations agent for TalkFlow Speech Recognition Agent."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
from openai import AsyncOpenAI
from agents import (
    Agent,
    OpenAIChatCompletionsModel,
    Runner,
    set_tracing_disabled,
)
from app.agents.instructions import STT_AGENT_INSTRUCTIONS
from app.agents.tools import (
    get_language_capabilities_fn,
    get_language_capabilities_tool,
    get_stt_status_fn,
    get_stt_status_tool,
    list_available_models_fn,
    list_available_models_tool,
    list_stt_providers_fn,
    list_stt_providers_tool,
    recommend_stt_profile_fn,
    recommend_stt_profile_tool,
    research_stt_knowledge_tool,
    search_stt_docs_tool,
)
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("agents.brain")

# Disable remote telemetry export
try:
    set_tracing_disabled(disabled=True)
except Exception:
    pass


class STTOperationsAgent:
    """Operations and diagnostic reasoning agent powered by OpenAI Agents SDK and local Ollama."""

    def __init__(self):
        self.enabled = settings.llm_agent.enabled
        self.model_name = settings.llm_agent.model
        self.base_url = settings.llm_agent.base_url
        self.api_key = settings.llm_agent.api_key

        self.client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
        )

        self.model = OpenAIChatCompletionsModel(
            model=self.model_name,
            openai_client=self.client,
        )

        self.agent = Agent(
            name="TalkFlow Speech Recognition Operations Agent",
            instructions=STT_AGENT_INSTRUCTIONS,
            model=self.model,
            tools=[
                get_stt_status_tool,
                list_stt_providers_tool,
                list_available_models_tool,
                get_language_capabilities_tool,
                recommend_stt_profile_tool,
                research_stt_knowledge_tool,
                search_stt_docs_tool,
            ],
        )

    async def run_diagnostics(self, query: str = "Check current STT operational health and recommend settings") -> str:
        """Executes operational reasoning task using OpenAI Agents SDK or fast-path fallback."""
        if not self.enabled:
            return "Operational reasoning brain is disabled via configuration."

        try:
            result = await asyncio.wait_for(
                Runner.run(self.agent, query),
                timeout=settings.llm_agent.timeout_seconds,
            )
            return str(result.final_output)
        except Exception as exc:
            log.warning(f"Ollama operational reasoning offline or timed out: {exc}. Using deterministic diagnostic summary.")
            # Deterministic fast-path summary
            status = get_stt_status_fn()
            rec = recommend_stt_profile_fn("cpu", "en")
            return (
                f"[Operational Diagnostic Summary (Fast-Path)]\n"
                f"- STT Service: {status['status']} ({status['agent_name']} v{status['version']})\n"
                f"- Primary Engine: {status['provider']} ({status['model_size']}, precision: {status['compute_type']}, threads: {status['cpu_threads']})\n"
                f"- Recommendation: {rec['recommended_model']} on {rec['device']} ({rec['reasoning']})"
            )


stt_brain = STTOperationsAgent()

