---
name: test-audit
description: "Test suite audit and gap analysis. Evaluates test coverage, brittle tests, flakiness, missing failure-injection scenarios, and mutation test resistance."
---

# Test Suite Audit Mode

Examine test coverage across unit, integration, and end-to-end layers to identify blind spots and unverified failure modes.

## Audit Workflow
1. **Catalog Existing Tests**: Map test files to product modules, services, and API routes.
2. **Identify Blind Spots**: Pinpoint untested error branches, network drops, rate limits, schema validations, and concurrent operations.
3. **Flakiness & Isolation Assessment**: Detect hardcoded ports, shared database state across parallel workers, unhandled timers, and un-mocked external network calls.
4. **Resilience & Chaos Scenarios**: Verify behavior when Redis is unreachable, AI models time out, or database connection drops.
5. **Action Plan**: Prioritize missing tests that guard critical customer workflows and security boundaries.
