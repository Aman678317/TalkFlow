# TalkFlow Search Test Matrix

## Contract under test

Route: `GET /api/v1/search?q=...`  
Authentication: authenticated organization user  
Response categories: `meetings`, `segments`, `documents`, `chat_messages`, `glossary_terms`, `tm_entries`

## Cases

| Area | Case | Expected |
|---|---|---|
| Query | Leading/trailing/repeated whitespace | Normalized once; harmless |
| Query | Empty / whitespace-only | Empty category lists; no match-all |
| Query | Punctuation-only PostgreSQL query | Empty transcript/chat retrieval; no tsquery syntax error |
| Query | Prefix term | PostgreSQL prefix full-text retrieval works |
| Query | Unicode words | Preserved as Unicode query terms |
| Query | Operator-looking input (`&`, `!`, `:`, parentheses) | Treated as user text, not raw tsquery operators |
| Query | Query over 200 characters | Service boundary and route enforce the maximum |
| Transcripts | Match canonical source | Returns final segment and owning meeting |
| Transcripts | Match translated derivative | Returns linked segment with `matched_field=translation`, `matched_text` and `target_lang` |
| Consistency | Non-final source segment | Excluded from search |
| TM | Match source text | Entry returned |
| TM | Match target text | Entry returned |
| Tenant | Another organization owns matching content | No result leakage |
| Fallback | SQLite dialect | Uses portable `LIKE` backend |
| Contract | All search categories | Stable response category keys |
| Read-only | Search request | No writes, model invocation or translation job creation |
| Ordering | Multiple matching rows | Newest first within category, per existing contract |

## Test commands

From repository root in CI-compatible Python 3.11 environment:

```bash
APP_ENV=test CACHE_BACKEND=memory REDIS_URL="" \
JWT_SECRET=ci-jwt-secret-0123456789abcdef0123456789 \
python -m pytest tests/integration/test_api.py -q

APP_ENV=test CACHE_BACKEND=memory REDIS_URL="" \
JWT_SECRET=ci-jwt-secret-0123456789abcdef0123456789 \
python -m pytest tests/test_history_filters_hardened.py -q

cd apps/web
npm ci --no-audit --no-fund
npx tsc -b
npx vitest run
npx vite build
```

The initial implementation should add a dedicated `tests/integration/test_search.py` regression suite. CI green is required; local execution must be reported separately from GitHub Actions evidence.
