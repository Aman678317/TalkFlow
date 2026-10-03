---
name: devex-review
description: "Developer experience, environment setup, and onboarding audit. Evaluates local dev setup speed, documentation accuracy, dependency pinning, and ease of contribution."
---

# Developer Experience & Onboarding Review (DevEx)

Audit and optimize the local setup, developer tooling, documentation, and onboarding flow.

## Evaluation Dimensions
1. **Zero to Running**: Can a new developer clone, configure `.env`, install dependencies, and launch both backend and frontend without undocumented steps or missing files?
2. **Setup Simplicity**: Are prerequisites clearly stated? Are platform-specific paths (Windows/Linux/macOS) accounted for?
3. **Configuration & Defaults**: Are safe local defaults provided? Is `.env.example` complete and up-to-date?
4. **Tooling & Scripts**: Are one-click or single-command launch scripts (`START_ALL.bat`, `npm run dev`, `python run_api.py`) functioning and robust?
5. **Fast Feedback Loop**: Are typechecking, linting, and fast-lane unit tests speedy and decoupled from heavy production infrastructure like external Redis or GPU drivers?
6. **Error Messages**: When misconfigured, does the system fail with descriptive, actionable error messages rather than cryptic tracebacks?

## Output Artifact
Provide a structured DevEx review:
- Friction Points & Onboarding Blockers
- Dependency & Requirement Fixes
- Script & Tooling Improvements
- Documentation Gaps
- DevEx Quality Score (1-10)
