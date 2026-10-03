---
name: investigate
description: "Root-cause bug investigation. Formulates hypotheses, designs reproducing probes, isolates minimal failing cases, and proves causes before modifying code."
---

# Bug Investigation Mode

Diagnose bugs systematically without guessing or applying trial-and-error edits.

## Investigation Protocol
1. **Understand Symptoms**: Gather exact error messages, stack traces, environment details, and user steps.
2. **Minimal Reproduction**: Write an automated test case or minimal script that reliably reproduces the defect.
3. **Trace Execution Path**: Trace inputs through middleware, handlers, services, and persistence layers.
4. **Isolate Root Cause**: Distinguish symptoms from underlying flaws (e.g. stale state, unhandled promise, timezone mismatch, race condition).
5. **Verify Hypotheses**: Prove the cause with logs, breakpoints, or targeted test assertions before touching production code.
6. **Formulate Minimal Fix**: Specify the smallest effective change that resolves the bug and prevents regression.
