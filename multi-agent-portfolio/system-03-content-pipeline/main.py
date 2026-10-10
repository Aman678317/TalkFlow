"""System 03: Autonomous Content Pipeline - Main Demonstration.

Demonstrates the self-correcting hybrid pipeline (LangGraph + CrewAI)
with research sub-crew, draft generation, critique scoring, and quality gates.
"""

import sys
from pathlib import Path

# Add current directory and root to sys.path
CURRENT_DIR = Path(__file__).resolve().parent
ROOT = CURRENT_DIR.parent
for p in [str(CURRENT_DIR), str(ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from graph import build_content_pipeline


def run(topic: str = "Why agentic AI needs typed tool calls"):
    """Execute the autonomous content pipeline."""
    print("==================================================================")
    print("  [System 03] Autonomous Content Pipeline (LangGraph + CrewAI)")
    print(f"  Topic: {topic}")
    print("==================================================================")

    app = build_content_pipeline()
    initial_state = {
        "topic": topic,
        "research": "",
        "draft": "",
        "score": 0.0,
        "feedback": [],
        "loops": 0,
        "final_content": None,
        "published_path": None,
        "status": "in_progress",
    }

    result = app.invoke(initial_state)

    print("\n==================================================================")
    print("              CONTENT PIPELINE EXECUTION SUMMARY                  ")
    print("==================================================================")
    print(f"Status:            {result.get('status')}")
    print(f"Final Score:       {result.get('score'):.2f} / 1.00")
    print(f"Revision Cycles:   {result.get('loops')} passes completed")
    print(f"Output File:       {result.get('published_path')}")
    print("==================================================================")
    print("\nPublished Excerpt:")
    lines = (result.get("final_content") or "").splitlines()
    print("\n".join(lines[:20]))
    print("...\n")
    return result


if __name__ == "__main__":
    custom_topic = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Why agentic AI needs typed tool calls"
    run(custom_topic)
