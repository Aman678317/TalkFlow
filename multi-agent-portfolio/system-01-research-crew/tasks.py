"""System 01: Research Assistant Crew - Task Definitions.

Defines the individual tasks executed sequentially by the research crew.
"""

from crewai import Task


def create_search_task(agent, topic: str) -> Task:
    """Create task for Senior Research Librarian."""
    return Task(
        description=(
            f"Search for authoritative, primary, and recent technical sources regarding: '{topic}'. "
            "Identify 5–8 credible links from engineering blogs, official documentation, whitepapers, or benchmarks. "
            "For each source, provide: Title, URL, and a 1-sentence note explaining why it is relevant."
        ),
        expected_output="A structured list of 5–8 credible sources with title, URL, and 1-line relevance note.",
        agent=agent,
    )


def create_analysis_task(agent, context_tasks: list) -> Task:
    """Create task for Critical Research Analyst."""
    return Task(
        description=(
            "Review all sources provided by the Search Agent. Extract the 3–5 strongest, most defensible claims. "
            "For each claim: cite the exact source URL, provide the supporting evidence or benchmark figures, "
            "and explicitly flag any unsupported or vague claims. Do not blend disparate claims together."
        ),
        expected_output="3–5 verified claims with explicit supporting evidence, source citations, and flagged uncertainties.",
        agent=agent,
        context=context_tasks,
    )


def create_write_task(agent, context_tasks: list) -> Task:
    """Create task for Technical Report Writer."""
    return Task(
        description=(
            "Turn the analyzed claims and evidence into a high-density, professional technical report. "
            "Format requirements:\n"
            "1. A concise 2-sentence executive summary at the top.\n"
            "2. 3–5 headed sections explaining each core finding and trade-off with clear engineering depth.\n"
            "3. A clean 'References & Primary Sources' list at the bottom.\n"
            "Strict constraint: Open with the answer immediately. No filler intros ('In this article we will explore...')."
        ),
        expected_output="A complete Markdown technical report with a 2-sentence summary, 3–5 headed sections, and sources list.",
        agent=agent,
        context=context_tasks,
    )


def create_fact_check_task(agent, context_tasks: list) -> Task:
    """Create task for Fact-Checker Agent (Level-Up Idea)."""
    return Task(
        description=(
            "Audit the generated report against the original search sources. Verify that every single statistic, "
            "claim, and quotation is accurately represented. Append a 'Fact-Check Verification Stamp' confirming "
            "traceability and flagging any claim that lacks direct primary evidence."
        ),
        expected_output="The final audited report with a verification stamp validating factual integrity.",
        agent=agent,
        context=context_tasks,
    )
