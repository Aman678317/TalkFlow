# TalkFlow Search — 10-Day Implementation Plan

**Owner:** AMAN  
**Plan starts:** 2026-10-23  
**Working branch:** `AMAN`  
**Scope:** Notes-inspired search over meeting transcripts, translated transcript derivatives, meetings, chat, documents, glossary terms, and translation memory.

## Delivery principle

Ship additive, tenant-safe improvements without rebuilding auth, changing database schema unnecessarily, renaming the current API, or changing the canonical source-of-truth contract. The current response remains `SearchResponse` categories. No day is complete due to elapsed time alone: exit criteria must pass.

## Day-by-day plan

### Day 1 — Evidence and baseline
- Inspect canonical backend, endpoint, schema, frontend call sites, models and CI workflow.
- Capture branch/base SHA and CI evidence.
- Write reverse-engineering evidence document.
- **Exit:** code locations and behavior link to actual files; private Notes details are labeled as assumptions.

### Day 2 — Query input safety
- Add whitespace normalization, length and term bounds, safe full-text query construction, and empty-query handling.
- Preserve endpoint limits and current categories.
- Test punctuation-only queries, operator-looking input, whitespace, Unicode and long terms.
- **Exit:** user input cannot become raw tsquery operators; empty query is not a broad listing.

### Day 3 — Multi-field retrieval
- Search final canonical transcripts and linked target-language translation rows.
- Return match-field metadata for translated hits without replacing canonical source text.
- Search source and target text in translation memory.
- **Exit:** source and translated speech can each find the relevant transcript; canonical source stays unchanged.

### Day 4 — Tenant isolation
- Verify organization scoping on every joined and direct-table search.
- Add cross-tenant fixtures covering meetings, transcripts, translations, chat, documents, glossary and TM.
- **Exit:** organization B never observes organization A results, including derivative rows.

### Day 5 — Relevance and result contracts
- Define category ordering, deterministic tie-breaking and match-field metadata.
- Keep current categorized JSON shape; document ranking limitations.
- Add API contract tests for response keys, bounds and empty-query behavior.
- **Exit:** deterministic results with no response-shape break.

### Day 6 — Search UX
- Review existing search callers and add a debounced, accessible surface only where it fits current UI.
- Keyboard focus, clear action, loading/empty/error states, safe result highlighting.
- **Exit:** user can search and recover cleanly from zero results or API errors.

### Day 7 — Performance baseline
- Seed representative transcripts and metadata; measure common query latency in SQLite and PostgreSQL.
- Inspect query plans before adding GIN/generated indexes.
- **Exit:** baseline records dataset size, queries, backend, p50/p95, and plans; indexes are evidence-led.

### Day 8 — Reliability
- Test DB/provider-independent search, backend selection, duplicate translated hits, missing source relations, and query bounds.
- Confirm search does not invoke translation or inference.
- **Exit:** read-only and deterministic under expected failure modes.

### Day 9 — Full CI and manual QA
- Run backend unit/integration tests, frontend Vitest, strict TypeScript, Vite build, migrations, Docker and browser smoke jobs available in CI.
- Run keyboard and mobile viewport checks; document tests not possible in the environment.
- **Exit:** required jobs green, no unresolved search-specific failures, QA checklist recorded.

### Day 10 — Release decision
- Review final diff, secret scan, tenant-boundary tests, schema impact, API compatibility and rollback.
- Confirm the `AMAN` branch is the only branch created for this work and pushed successfully.
- **Exit:** evidence-backed GO/NO-GO decision; do not merge to main without explicit review.

## Acceptance checklist

- [ ] Endpoint remains authenticated and organization-scoped.
- [ ] Query is normalized and bounded.
- [ ] PostgreSQL input becomes a safe prefix query; malformed operator syntax cannot break search.
- [ ] SQLite and PostgreSQL preserve the same output keys.
- [ ] Final canonical transcript source text is searched.
- [ ] Linked translated transcript derivatives can be found.
- [ ] Translation memory matches source and target terms.
- [ ] Empty query is not match-all.
- [ ] Cross-tenant tests cover direct and joined resources.
- [ ] Tests cover Unicode, apostrophes, punctuation, whitespace and long input.
- [ ] No database schema change without migration review.
- [ ] Frontend/API contract unchanged or additive.
- [ ] CI results and QA gaps recorded honestly.
- [ ] Rollback is a revert of the `AMAN` branch commits.

## Rollback

Revert the search-service commit(s) on `AMAN`. No schema migration is included in the initial improvement. Existing endpoint and response contracts are retained to avoid stranding clients on a new wire format.
