---
name: code-review
description: "Comprehensive code review for correctness, clarity, security, performance, test coverage, and adherence to project conventions."
---

# Code Review Mode

Review changes or existing code thoroughly with evidence-based findings before merging or approving.

## Review Principles
1. **Correctness First**: Verify logic handles nil/null, boundary conditions, array bounds, type narrowing, and async order.
2. **Defensive Programming**: Unhandled promises, unclosed resources, memory leaks, uncancelled timeouts/intervals.
3. **Simplicity & Anti-Bloat**: Avoid speculative abstractions, unnecessary dependencies, and redundant code paths.
4. **Security & Data Safety**: No unsanitized inputs, no exposed secrets, no SQL/command/prompt injection, correct permission checks.
5. **Observability & Debuggability**: Meaningful error messages, appropriate log levels, structured context.
6. **Output Format**: Format findings as `[File:Line] - Severity (P0/P1/P2) - Description & Recommended Drop-in Fix`.
