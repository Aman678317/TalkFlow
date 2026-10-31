"""Autonomous Research Engine and tools for TalkFlow agents."""
from rag.research.engine import AutonomousResearchEngine
from rag.research.scopes import AGENT_RESEARCH_TOPICS
from rag.research.tools import ResearchTools
from rag.research.web_search import WebSearchProvider

__all__ = [
    "AutonomousResearchEngine",
    "AGENT_RESEARCH_TOPICS",
    "ResearchTools",
    "WebSearchProvider",
]

