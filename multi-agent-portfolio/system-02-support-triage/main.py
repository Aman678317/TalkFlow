"""System 02: Customer Support Triage Graph - Main Demonstration.

Demonstrates conditional routing across specialist nodes and automatic human escalation.
"""

import sys
from pathlib import Path

# Add current directory and root to sys.path
CURRENT_DIR = Path(__file__).resolve().parent
ROOT = CURRENT_DIR.parent
for p in [str(CURRENT_DIR), str(ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from graph import build_triage_graph


def run_ticket_triage(ticket_text: str, thread_id: str = "triage_session_01"):
    """Invoke the triage graph on a given support ticket."""
    app = build_triage_graph(use_memory_checkpointer=True)
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "ticket": ticket_text,
        "category": "",
        "confidence": 0.0,
        "reasoning": "",
        "route": "",
        "sentiment": "neutral",
        "response": None,
        "escalated": False,
        "escalation_reason": None,
        "history": [],
    }

    print(f"\nIncoming Ticket: \"{ticket_text}\"")
    output = app.invoke(initial_state, config=config)

    print(f"-> Classification: Category='{output['category']}', Confidence={output['confidence']:.2f}, Sentiment='{output['sentiment']}'")
    print(f"-> Routing Edge:   '{output['route']}'")
    print(f"-> Escalated:      {output['escalated']}")
    print(f"-> Final Output:\n{output['response']}\n" + "-" * 60)
    return output


def run_all_scenarios():
    """Run the 3 core benchmark scenarios from the build guide."""
    print("==================================================================")
    print("  [System 02] Customer Support Triage Graph (LangGraph)")
    print("==================================================================")

    # 1. Billing Ticket
    run_ticket_triage(
        "I was charged twice this month for my subscription order ord_101. Please refund me.",
        thread_id="test_billing_01",
    )

    # 2. Technical Support Ticket
    run_ticket_triage(
        "My WebRTC microphone audio has high latency and packet lag during calls.",
        thread_id="test_tech_01",
    )

    # 3. Angry / Low-Confidence Escalation
    run_ticket_triage(
        "This is ridiculous and unacceptable, your platform is a scam, get a human now!",
        thread_id="test_escalate_01",
    )


if __name__ == "__main__":
    if len(sys.argv) > 1:
        custom_ticket = " ".join(sys.argv[1:])
        run_ticket_triage(custom_ticket)
    else:
        run_all_scenarios()
