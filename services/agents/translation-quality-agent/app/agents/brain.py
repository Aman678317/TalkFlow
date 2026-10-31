"""Translation Quality Operations Agent Brain using OpenAI Agents SDK and Ollama."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
from app.agents.instructions import QUALITY_BRAIN_INSTRUCTIONS
from app.agents.tools import ALL_QA_TOOLS
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("agents.brain")


class QualityOperationsBrain:
    """Out-of-band reasoning agent for quality telemetry, policy advice, and diagnostics."""

    def __init__(self) -> None:
        self.enabled = settings.llm_agent.enabled
        self.model = settings.llm_agent.model
        self.base_url = settings.llm_agent.base_url
        self._agent = None
        self._init_attempted = False

    def _init_agent(self) -> None:
        if self._init_attempted:
            return
        self._init_attempted = True
        if not self.enabled:
            return

        try:
            from agents import Agent, OpenAIChatCompletionsModel
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=settings.llm_agent.api_key or "ollama",
            )

            model_wrapper = OpenAIChatCompletionsModel(
                model=self.model,
                openai_client=client,
            )

            self._agent = Agent(
                name="Translation Quality Operations Specialist",
                instructions=QUALITY_BRAIN_INSTRUCTIONS,
                tools=ALL_QA_TOOLS,
                model=model_wrapper,
            )
            log.info(f"Initialized Translation Quality Operations Brain with model {self.model} at {self.base_url}")
        except Exception as exc:
            log.warning(f"Could not initialize OpenAI Agents SDK Brain ({exc}). Deterministic QA remains fully operational.")
            self._agent = None

    async def run_diagnostic(self, query: str) -> Dict[str, Any]:
        """Runs an out-of-band operational diagnostic query."""
        self._init_agent()
        if not self._agent:
            return {
                "brain_active": False,
                "reason": "Ollama Brain disabled or unconfigured",
                "answer": f"Deterministic diagnostic: Quality Agent running on port {settings.api.port}.",
            }

        try:
            from agents import Runner
            res = await Runner.run(self._agent, input=query)
            return {
                "brain_active": True,
                "model": self.model,
                "answer": str(res.final_output),
            }
        except Exception as exc:
            return {
                "brain_active": False,
                "error": str(exc),
                "answer": "Fallback: Deterministic quality evaluation active.",
            }


quality_brain = QualityOperationsBrain()

