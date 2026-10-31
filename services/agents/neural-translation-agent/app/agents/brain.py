"""OpenAI Agents SDK operations agent powered by local Ollama."""
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
from app.agents.instructions import MT_AGENT_INSTRUCTIONS
from app.agents.tools import ALL_MT_TOOLS
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("agents.brain")

try:
    set_tracing_disabled(disabled=True)
except Exception:
    pass


class TranslationOperationsAgent:
    """Operations and diagnostic reasoning agent for Agent 04."""

    def __init__(self) -> None:
        self.enabled = settings.llm_agent.enabled
        self.model_name = settings.llm_agent.model
        self.base_url = settings.llm_agent.base_url
        self.api_key = settings.llm_agent.api_key

        self.client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
        )

        self._agent: Optional[Agent] = None
        if self.enabled:
            self._init_agent()

    def _init_agent(self) -> None:
        try:
            model = OpenAIChatCompletionsModel(
                model=self.model_name,
                openai_client=self.client,
            )
            self._agent = Agent(
                name="TranslationOpsBrain",
                instructions=MT_AGENT_INSTRUCTIONS,
                model=model,
                tools=ALL_MT_TOOLS,
            )
            log.info(f"OpenAI Agents SDK brain initialized with model: {self.model_name}")
        except Exception as e:
            log.warning(f"Failed to initialize OpenAI Agents SDK brain: {e}")
            self._agent = None

    async def diagnose_issue(self, query: str) -> str:
        """Runs operational diagnostic query through the reasoning agent."""
        if not self.enabled or not self._agent:
            return f"Agent brain is disabled or unavailable. (Configured model: {self.model_name})"

        try:
            result = await Runner.run(self._agent, input=query)
            return str(result.final_output)
        except Exception as e:
            log.error(f"Reasoning agent failed during query: {e}")
            return f"Diagnostic analysis error: {e}"


mt_operations_agent = TranslationOperationsAgent()

