---
name: plan-eng-review
description: "Engineering architecture and implementation plan review. Evaluates system boundaries, data contracts, failure modes, concurrency, scalability, and test strategy."
---

# Plan Engineering & Architecture Review Mode

Review technical designs, architectural plans, and implementation specs through a principal engineer lens before writing code.

## Evaluation Dimensions
1. **Component Boundaries & Coupling**: Are concerns cleanly separated? Are interfaces minimal, typed, and well-specified?
2. **Data Flow & State Management**: How does state transition from client to server to persistence? Are there race conditions, stale reads, or double writes?
3. **Failure Modes & Resilience**: What happens when Redis, database, external APIs, or WebSocket drops? Are timeouts, backoffs, circuit breakers, and fallbacks in place?
4. **Concurrency & Load**: How does the system behave under concurrent requests, burst traffic, or reconnect storms?
5. **Observability**: Are distributed traces, structured logs, request IDs, and metrics emitted across the request path?
6. **Testing & Verification**: What tests prove correctness? Are unit, integration, edge-case, and failure-injection tests explicitly planned?

## Output Artifact
Provide a structured technical review:
- Critical Architectural Vulnerabilities (blockers)
- Recommended Refinements (high impact)
- Verified Strengths
- Final Verdict (Approve / Request Changes)
