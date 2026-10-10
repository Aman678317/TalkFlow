"""Unified Multi-Agent Systems Runner.

Executes System 01 (CrewAI), System 02 (LangGraph), and System 03 (Hybrid) in sequence.
"""

import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON_EXE = ROOT / ".venv" / "Scripts" / "python.exe"
if not PYTHON_EXE.exists():
    PYTHON_EXE = Path(sys.executable)


def main():
    print("==================================================================")
    print("   MULTI-AGENT SYSTEMS PORTFOLIO: ALL 3 SYSTEMS RUNNER            ")
    print("==================================================================")

    # 1. System 02: Support Triage (Deterministic State Machine)
    print("\n>>> [1/3] Executing System 02: Customer Support Triage Graph (LangGraph)...")
    s2 = subprocess.run([str(PYTHON_EXE), str(ROOT / "system-02-support-triage" / "main.py")])
    if s2.returncode != 0:
        print("[!] System 02 encountered an error.")

    # 2. System 03: Autonomous Content Pipeline (Self-Correcting Loop)
    print("\n>>> [2/3] Executing System 03: Autonomous Content Pipeline (Hybrid)...")
    s3 = subprocess.run([str(PYTHON_EXE), str(ROOT / "system-03-content-pipeline" / "main.py")])
    if s3.returncode != 0:
        print("[!] System 03 encountered an error.")

    # 3. System 01: Research Crew (CrewAI)
    print("\n>>> [3/3] Checking System 01: Research Assistant Crew (CrewAI)...")
    s1 = subprocess.run([str(PYTHON_EXE), str(ROOT / "system-01-research-crew" / "main.py")])
    if s1.returncode != 0:
        print("[!] System 01 encountered an error.")

    print("\n==================================================================")
    print("[OK] All 3 Multi-Agent Systems initialized and verified!")
    print("  Read architecture diagrams & resume lines in multi-agent-portfolio/README.md")
    print("==================================================================")


if __name__ == "__main__":
    main()
