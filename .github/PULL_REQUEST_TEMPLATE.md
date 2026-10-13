# GlobalTalk AI — Pull Request

> _Please submit only **one feature or fix** per pull request._

---

## PR Checklist

- [ ] I have read and agree to the [Code of Conduct](CODE_OF_CONDUCT.md)
- [ ] I have read the [Contributing Guidelines](CONTRIBUTING.md)
- [ ] This PR contains only one logical change or feature
- [ ] Tests are included for new functionality
- [ ] All existing tests pass (`pytest tests/` and `cd apps/web && npm test`)
- [ ] Documentation has been updated if behavior or API changes
- [ ] Commit messages follow the [Conventional Commits](https://www.conventionalcommits.org/) format
- [ ] I have rebased onto the latest `main` branch

---

## Type of Change

- [ ] 🐛 Bug fix (non-breaking change that fixes an issue)
- [ ] ✨ New feature (non-breaking change that adds functionality)
- [ ] 💥 Breaking change (fix or feature that changes existing behavior)
- [ ] 📖 Documentation update
- [ ] 🧹 Refactoring (no functional change)
- [ ] ⚡ Performance improvement
- [ ] 🔒 Security fix

---

## Description

<!-- Briefly describe what this PR does and why. -->

### What changed?

### Why was this change needed?

### How was it tested?

---

## Related Issues

<!-- Link any related issues: "Fixes #123" or "Closes #456" -->

Fixes #

---

## Screenshots / Demo (if applicable)

<!-- Add screenshots, screen recordings, or GIFs showing the change. -->

---

## Additional Notes

<!-- Anything else the reviewer should know? -->

---

## AI-Aware Review Depth

> Based on the [State of AI vs. Human Code Generation Report](https://www.coderabbit.ai) (2026):
> AI co-authored PRs show ~1.7× more findings overall, with the largest spikes in
> logic/correctness (1.75×), error handling (~2×), readability (3.15×), credential
> handling (1.88×), and excessive I/O (~8×). If **any part** of this change was written
> or refactored by an AI assistant (Claude, Cursor, Copilot, Codex, Qoder, etc.), tick
> "AI-assisted" below and answer every question that applies. Reviewers: hold AI-assisted
> PRs to this checklist explicitly — do not trust the model that added the error to find it.

- [ ] This PR is: entirely human-authored / AI-assisted / fully AI-generated
- [ ] Project context was provided to the assistant (AGENTS.md, module docs, related code)

**Correctness & control flow** (highest-risk AI category)
- [ ] Every new error/exception path is tested, including negative and edge cases
- [ ] No exception is swallowed silently — failures emit a user-visible event or log
- [ ] Null/None dereference risks checked at module boundaries; types asserted where inferred
- [ ] Concurrency primitives reviewed: shared mutable state, lock ordering, task cancellation
- [ ] Operation ordering / dependency flow is intentional, not incidental

**Security**
- [ ] Passwords/credentials go only through the approved helpers (`globaltalk.core.security`, env-based settings) — never ad-hoc hashing or inline literals
- [ ] No object references taken from user input without authorization checks (IDOR)
- [ ] New inputs validated at system boundaries; no raw interpolation into SQL/HTML/shell

**Realtime pipeline specifics** (TalkFlow)
- [ ] On provider failure (`ProviderUnavailable`), the meeting degrades explicitly (`translation.failed` / `quality.degraded`) and the original audio path is untouched
- [ ] Canonical transcript segments remain immutable; derivatives carry `source_segment_id`
- [ ] Fan-out deduplicates per (segment, target language); TTS runs once per language group
- [ ] Latency budget per stage still measured; no synchronous model call added on the WS event loop

**Quality & efficiency**
- [ ] Code follows the local idioms of the touched module (naming, structure, comment style)
- [ ] No unused/redundant code left behind by generation iterations
- [ ] No new I/O in hot paths without batching or pagination; no repeated reads of the same resource
- [ ] `pytest tests/unit -q` passes locally with the diff applied
