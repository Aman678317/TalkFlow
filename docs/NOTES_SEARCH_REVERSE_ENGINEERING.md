# Notes App Search: Reverse Engineering and Evidence

**Status:** evidence review + implementation design  
**Repository:** [Aman678317/TalkFlow](https://github.com/Aman678317/TalkFlow)  
**Date:** 2026-10-23

## 1. Executive summary

Notes-style search feels fast because search is treated as a product capability, not a single text input wired to a broad SQL query. A robust design separates query normalization, retrieval, filters, ranking, snippets, and result navigation. Full-text indexes are useful where the database supports them; a portable fallback can remain useful if both paths preserve the same security and result contract.

**Evidence distinction:** the attached source describes an Apple Notes / Google Keep-style architecture (inverted indexes, OCR, facets, field weighting) and includes a proposed TypeScript in-memory index. These are research hypotheses and sample code, not proof of Apple’s private implementation or TalkFlow code. This document separates those assertions from directly inspected repository evidence.

## 2. What was inspected

The live repository default branch was `main`, at commit `e8a90f76b52e9ffc7c670b5b19c018cddfef75fe` during this review. The default branch README identifies a React 18/Vite/TypeScript frontend and a FastAPI/SQLAlchemy backend, and explicitly calls `services/api` canonical while `apps/api` is a legacy compatibility tree.

Direct repository evidence:
- [Search service](../services/api/app/services/search_service.py): `SearchBackend` protocol, `PostgresSearch`, `LikeSearch`, dialect-based backend selection, organization scoping.
- [Search route](../services/api/app/routers/platform.py): `GET /api/v1/search?q=...`, requires `require_org_user`, returns `SearchResponse`.
- [Search response schema](../services/api/app/schemas.py): stable collection keys `meetings`, `segments`, `documents`, `chat_messages`, `glossary_terms`, `tm_entries`.
- [Canonical data models](../services/api/app/db/models.py): transcript source rows and translation derivatives are separate; a transcript is documented as the canonical human source.
- [Frontend scripts](../apps/web/package.json): Vitest, TypeScript, Vite build.
- [Testing guide](TESTING.md): existing test layers and canonical commands.

## 3. Observed baseline behavior

The canonical service chooses PostgreSQL search when the bound SQLAlchemy engine dialect is PostgreSQL; otherwise it selects the SQLite development/test `LIKE` backend. Before this branch's patch:
- PostgreSQL built prefix `tsquery` by joining raw whitespace-separated terms with `&`, without explicit normalization or escaping.
- PostgreSQL used `to_tsvector('simple', ...)` for transcript source text and chat message text.
- Both backends searched meetings by title and documents by filename.
- Both backends scoped transcript/chat queries through the owning meeting's `org_id`; direct-organization tables scoped on `org_id`.
- Glossary terms searched source and target text.
- Translation memory originally searched source text only.
- Results were ordered by creation time, not relevance score.
- The response contract was categorized lists, not a globally ranked result stream.
- The service originally searched transcript source text only, not linked target-language translation text.

## 4. Proposed Notes-inspired architecture

```text
Input
  -> normalize and bound query
  -> parse plain terms / explicit filters (future)
  -> retrieve candidates
       PostgreSQL: safe prefix full-text query
       SQLite: portable substring fallback
       translation derivatives: linked to canonical transcript
       metadata: title, filename, speaker, language, date (future facets)
  -> enforce tenant scope in every DB query
  -> annotate match field and snippet
  -> deterministic relevance ranking (future/global result stream)
  -> return stable category lists + query metadata
```

Suggested later enhancements (do not claim implemented until they land):
- Debounced UI and keyboard navigation; preserve focus and provide empty/loading states.
- Field boosts (title > transcript > translated transcript > metadata).
- Filters for date range, speaker, language, meeting, and result type.
- Snippet highlighting with safe rendering; never inject user text as HTML.
- Generated `tsvector` + GIN indexes only after query plans demonstrate a need.
- OCR indexing only if supported attachments and privacy/retention policy are reviewed.
- Language-aware tokenization/stemming per corpus; PostgreSQL's `simple` configuration is not language-specific stemming.
- A globally ranked result stream only as a versioned/additive API contract, not a breaking change.

## 5. What is not verified

This review does not establish the private internals of Apple Notes or Google Keep. It does not prove that Apple Notes uses SQLite FTS5, exposes BM25 weights, stores every handwriting/OCR term in a specific hidden index, or parses public `has:` filters. Those details are not established by the repository evidence here. The attached source's assertions should be treated as an architectural model, not vendor source code.

## 6. Verification links

- [Canonical search implementation](https://github.com/Aman678317/TalkFlow/blob/main/services/api/app/services/search_service.py)
- [Search endpoint](https://github.com/Aman678317/TalkFlow/blob/main/services/api/app/routers/platform.py)
- [Search response type](https://github.com/Aman678317/TalkFlow/blob/main/services/api/app/schemas.py)
- [Canonical database models](https://github.com/Aman678317/TalkFlow/blob/main/services/api/app/db/models.py)
- [Repository CI workflow](https://github.com/Aman678317/TalkFlow/blob/main/.github/workflows/ci.yml)
