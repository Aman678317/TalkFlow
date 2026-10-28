# Environment Matrix — TalkFlow / GlobalTalk AI

**Date:** 2026-10-29 · closes **G-019** (deployment environment drift) from
[`INITIAL_REPOSITORY_AND_DEEPL_GAP_REPORT.md`](INITIAL_REPOSITORY_AND_DEEPL_GAP_REPORT.md) §3
and [`11-initial-report-reconciliation.md`](11-initial-report-reconciliation.md)

## 1. Matrix

| Property | Local dev | Docker Compose | Render | Vercel (multi-service, staging+prod) | Legacy lane (`apps/api`) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| API entrypoint | `run_api.py` (`services/api`) | `docker-compose.yml` `api` service | `render.yaml` | Vercel `api` service → `services/api` `app.main:app` (`vercel.json` `services.api`) | `apps/api/globaltalk` (separate lineage) |
| API bind port | **8088** (canonically pinned; `vite.config.ts` refuses to proxy 8000 by design — comment at :34-38) | container-internal | `PORT` env (Render default **10000**) | serverless (no OS port); routed by platform rewrites | 8000 (dev-compat surface) |
| Frontend dev proxy | `/api`, `/api-docs`, WS → `ws://127.0.0.1:8088` (`vite.config.ts`) | n/a (built SPA) | n/a | same-origin rewrite `/api/:path*` → api service | n/a |
| Public API base (browser) | same-origin `""` (dev) | `:8000` surface if exposed | Render service URL | same-origin `""` — `api.ts` `DEFAULT_PRODUCTION_API_BASE_URL=""`, `VITE_API_BASE_URL` optional override (mixed-content upgrade guarded, `api.ts:174`) | — |
| WebSocket | `ws://127.0.0.1:8088` via dev proxy | same-origin ws through nginx/proxy | service wss | same-origin `wss://…/api` rewrite (ws:true) | — |
| Database | SQLite `./data/globaltalk.db` | `postgresql+asyncpg://globaltalk@postgres:5432` (Neon in prod docs) | Supabase pooler **:6543** / direct :5432 (`render.yaml`, Neon `stored_objects`) | Neon PostgreSQL (`DatabaseStorage`) | legacy `apps/api` version table |
| Cache/queue | in-process | Redis :6379 | Redis (`globaltalk-cache`) | Vercel KV/queue ("cache","queue" healthy per `/readyz`) | — |
| Health routes | `/healthz`,`/health`,`/api/v1/health`,`/readyz`,`/ready`,`/api/v1/ready` — all aliased | same | same | same (verified live 2026-10-29: all 6 → 200, checks `{database,cache,queue,storage}` = true) | own |
| Media transport | WS PCM (default), LiveKit when configured, P2P WebRTC | compose LiveKit :7880-7882 | enabled vars | E2E drills prove compose LiveKit; staging uses WS/LiveKit per env | — |
| Canonicality rule | **`services/api` only** | api service = `services/api` | `services/api` | `services/api` | **do not deploy as the HTTP API** |

## 2. Verified live (2026-10-29, this session)

- Staging `https://feat-vercel-multi-service.vercel.app`: all six health aliases → **200**,
  `/ready*` payload `{"ready":true,"checks":{"database":true,"cache":true,"queue":true,"storage":true}}`.
- Same-origin `/api/v1/*` from the SPA succeeds (no CORS/mixed-content errors observed in console).
- `/admin/*` client guard live; deep-link stubs present for documented routes
  (`translate/page` was 404 pre-fix — generator updated, deploy pending at write time).

## 3. Rules to keep drift closed

1. The browser never targets a port or host directly in production — always same-origin (or a
   `VITE_API_BASE_URL` override reviewed in the release packet).
2. Dev tooling MUST keep proxying 8088; 8000 is the legacy lane only (`vite.config.ts:34-38` comment
   is the canonical reference).
3. `apps/api` may run as a worker/legacy compatibility surface only; CI hardening lane and release
   notes must name the lineage of every migration in the artifact (G-005 companion).
4. Smoke test per environment = health-alias matrix above + one same-origin `/api/v1/languages`
   fetch from the SPA origin.
