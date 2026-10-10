"""System 02: Customer Support Triage Graph - StateGraph Definition.

Implements the LangGraph state machine with conditional routing and human escalation.
"""

import sys
from pathlib import Path

# Ensure current directory is in sys.path for local module resolution
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from nodes import (
    TicketState,
    classify_ticket,
    billing_agent,
    tech_agent,
    human_escalation,
)


def build_triage_graph(use_memory_checkpointer: bool = True):
    """Construct and compile the support triage StateGraph."""
    workflow = StateGraph(TicketState)

    # 1. Register Nodes
    workflow.add_node("classify", classify_ticket)
    workflow.add_node("billing", billing_agent)
    workflow.add_node("tech", tech_agent)
    workflow.add_node("escalate", human_escalation)

    # 2. Add Conditional Routing Edge
    workflow.add_conditional_edges(
        "classify",
        lambda state: state["route"],
        {
            "billing": "billing",
            "tech": "tech",
            "low_conf": "escalate",
        },
    )

    # 3. Entry point & Terminal edges
    workflow.set_entry_point("classify")
    workflow.add_edge("billing", END)
    workflow.add_edge("tech", END)
    workflow.add_edge("escalate", END)

    # 4. Optional Checkpointer for mid-conversation state recovery
    checkpointer = MemorySaver() if use_memory_checkpointer else None
    app = workflow.compile(checkpointer=checkpointer)
    return app


# Pre-compiled application instance
triage_app = build_triage_graph(use_memory_checkpointer=True)
