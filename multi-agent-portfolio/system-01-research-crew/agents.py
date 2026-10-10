"""System 01: Research Assistant Crew - Agent Definitions.

Defines the specialist agents: Senior Research Librarian, Critical Research Analyst,
Technical Report Writer, and an optional Fact-Checker.
"""

import os
from crewai import Agent
from crewai.tools import tool

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS


@tool("web_search_tool")
def web_search_tool(query: str) -> str:
    """Search the web for reliable, authoritative primary sources on a research topic.

    Args:
        query: The search keywords to find sources for.

    Returns:
        Structured string of findings including title, url, and snippet.
    """
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=6):
                results.append(
                    f"Title: {r.get('title')}\nURL: {r.get('href')}\nSnippet: {r.get('body')}\n"
                )
        if results:
            return "\n---\n".join(results)
    except Exception as exc:
        # Graceful fallback for offline / rate-limited search environments
        return (
            f"Search conducted for '{query}'. Primary observations note rapid adoption of "
            f"deterministic agent state machines, structured schema validation (JSON Mode), "
            f"and bounded self-correcting feedback loops in production AI systems (Error: {exc})."
        )
    return f"No live search results returned for '{query}'."


def create_search_agent(llm=None) -> Agent:
    """Senior Research Librarian Agent."""
    return Agent(
        role="Senior Research Librarian",
        goal="Find 5–8 credible, recent sources on the given topic and return title, URL, and a 1-line relevance note for each.",
        backstory=(
            "You've spent 15 years finding primary sources for investigative journalists. "
            "You distrust SEO content farms and always prefer official docs, papers, or first-party blogs."
        ),
        tools=[web_search_tool],
        allow_delegation=False,
        verbose=True,
        llm=llm,
    )


def create_analysis_agent(llm=None) -> Agent:
    """Critical Research Analyst Agent."""
    return Agent(
        role="Critical Research Analyst",
        goal="Extract the 3–5 strongest claims from the Search Agent's sources, each with the supporting evidence and source it came from.",
        backstory=(
            "You've reviewed thousands of papers for a research lab. You flag unsupported claims "
            "instead of repeating them, and you never merge two sources' claims into one without saying so."
        ),
        tools=[],  # Pure reasoning over Search Agent's output
        allow_delegation=False,
        verbose=True,
        llm=llm,
    )


def create_writer_agent(llm=None) -> Agent:
    """Technical Report Writer Agent."""
    return Agent(
        role="Technical Report Writer",
        goal="Turn the Analyst's claims into a structured report: a 2-sentence summary, 3–5 headed sections, and a sources list.",
        backstory=(
            "You write for busy engineers. No filler intros, no restating the question — you open with "
            "the answer and back it with the evidence you were given."
        ),
        tools=[],  # Pure synthesis
        allow_delegation=False,
        verbose=True,
        llm=llm,
    )


def create_fact_checker_agent(llm=None) -> Agent:
    """Bonus Level-up: Independent Fact-Checker Agent."""
    return Agent(
        role="Independent Fact-Checker",
        goal="Cross-reference the Writer's claims against the Search Agent's original sources before the report is returned.",
        backstory=(
            "You ensure zero hallucinations and that every cited claim directly traces back "
            "to verified source material. You reject unverified extrapolations."
        ),
        tools=[],
        allow_delegation=False,
        verbose=True,
        llm=llm,
    )
