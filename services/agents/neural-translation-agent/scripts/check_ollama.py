"""Probe checking Ollama local model availability and OpenAI Agents SDK reasoning brain."""
from __future__ import annotations

import asyncio
from app.agents.brain import mt_operations_agent


async def check() -> None:
    print("Checking OpenAI Agents SDK Operational Brain (Ollama)...")
    ans = await mt_operations_agent.diagnose_issue("What is the current status of Agent 04 translation providers?")
    print("\nOperational Brain Diagnostic Output:")
    print("-" * 60)
    print(ans)
    print("-" * 60)


if __name__ == "__main__":
    asyncio.run(check())

