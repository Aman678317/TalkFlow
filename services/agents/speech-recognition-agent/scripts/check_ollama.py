"""Check local Ollama server connectivity and test operational reasoning agent."""
import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.agents.brain import stt_brain
from app.core.config import settings


async def main():
    print("=" * 80)
    print("OLLAMA OPERATIONAL BRAIN & OPENAI AGENTS SDK PROBE")
    print("=" * 80)
    print(f"Enabled: {settings.llm_agent.enabled}")
    print(f"Base URL: {settings.llm_agent.base_url}")
    print(f"Model: {settings.llm_agent.model}")

    print("\nRunning test operational diagnostic query...")
    result = await stt_brain.run_diagnostics("Inspect STT service status and language coverage.")
    print("\nOperational Diagnostic Result:")
    print("-" * 60)
    print(result)
    print("-" * 60)
    print("\n[OK] Operational brain check completed.")


if __name__ == "__main__":
    asyncio.run(main())

