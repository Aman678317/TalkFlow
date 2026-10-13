# TalkFlow / GlobalTalk AI — Production Runbook & Operations Guide

**Audience**: DevOps Engineers, SREs, Systems Administrators  
**Stack**: FastAPI (Python 3.11+ / 3.14), React 18 / Vite, PostgreSQL, Redis, LiveKit SFU, Docker / Kubernetes

---

## 1. System Architecture & Component Ports

> **Which tree is running matters.** This repo holds two independent backends:
> **Tree A** = `services/api` (`app.*`, port 8088 locally) — the one Render deploys
> and the one every statement below refers to unless flagged otherwise.
> **Tree B** = `apps/api` (`globaltalk.*`, port 8000) — the legacy Makefile /
> golden-test tree; a few endpoints exist only there and are marked as such.

| Component | Container Name | Production Port | Health Endpoint |
|---|---|---|---|
| **API Gateway / Core Service** | `globaltalk-api` | `8088` (Tree A; `10000` from `$PORT` on Render) | `GET /health`, `GET /ready`, `GET /version` |
| **Frontend Web App** | `globaltalk-web` | `80` / `443` (or Vercel) | `GET /` |
| **Database** | `globaltalk-db` | `5432` (PostgreSQL) | `pg_isready` |
| **Cache & Realtime Queues** | `globaltalk-redis` | `6379` (Redis) | `PING` |
| **LiveKit SFU** | `globaltalk-livekit` | `7880` (HTTP) / `7881` (TCP) / `7882` (UDP) | `GET /` |

`GET /internal/components` exists only in **Tree B**; on Tree A the equivalent is
the `ai` object inside `GET /version` (see §3.2). LiveKit is optional and gated by
`LIVEKIT_ENABLED`; when disabled, meetings run on the plain WebSocket transport.

---

## 2. Environment Variables & Secrets Reference

### 2.1 Critical Production Configuration

Names below are the fields on `services/api/app/config.py` (Tree A), upper-cased —
that is what the app actually reads. `<…>` marks a value to supply, never to commit.

```bash
# --- Core environment ---
APP_ENV=production            # production turns on the fail-closed checks
LOG_LEVEL=INFO
SECRET_KEY=<32+ character random string>   # boot refuses to start without this
JWT_SECRET=<32+ character random string>   # ditto
JWT_ALGORITHM=HS256
JWT_ACCESS_TTL_MINUTES=30
JWT_REFRESH_TTL_DAYS=30

# --- Datastores ---
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/globaltalk
REDIS_URL=redis://:pass@host:6379/0        # empty string = no cache backend
CACHE_BACKEND=redis                        # auto | redis | memory

# --- Storage ---
S3_ENABLED=true
S3_ENDPOINT=https://s3.amazonaws.com
S3_BUCKET=globaltalk-production-storage
S3_ACCESS_KEY=<aws access key>             # note: S3_ACCESS_KEY, not S3_ACCESS_KEY_ID
S3_SECRET_KEY=<aws secret key>
S3_REGION=us-east-1
LOCAL_STORAGE_PATH=/tmp/storage            # only used when S3_ENABLED=false

# --- AI providers (each defaults to `auto`, which resolves to a preference list) ---
TRANSLATION_PROVIDER=<engine name>         # never leave `auto` in production
STT_PROVIDER=<engine name>
TTS_PROVIDER=<engine name>
LANG_DETECT_PROVIDER=langdetect
MODEL_CACHE_PATH=<directory holding the weights>   # default ./model_cache, forced to
                                                   # /tmp/model_cache on serverless

# --- Provider failure policy (defaults shown; docs/REALTIME.md explains each) ---
AI_TIMEOUT_S=8
AI_RETRY_BUDGET_S=20
RT_TRANSLATE_TIMEOUT_S=5
PROVIDER_COOLDOWN_S=30                     # doubles on each trip…
PROVIDER_MAX_COOLDOWN_S=600                # …up to this
RT_STALE_AFTER_MS=6000                     # a stage that has produced but stalled

# --- Realtime transport (LiveKit) ---
LIVEKIT_ENABLED=true                       # false = plain websocket transport
LIVEKIT_URL=wss://livekit.yourdomain.com
LIVEKIT_PUBLIC_URL=wss://…                 # the browser-reachable URL
LIVEKIT_API_KEY=<lk_api_key>
LIVEKIT_API_SECRET=<lk_api_secret>

# --- Security controls ---
CLAMAV_HOST=clamav                         # setting it enables scanning; there is no
CLAMAV_PORT=3310                           # separate enable flag. Unreachable ClamAV
                                           # FAILS CLOSED: uploads are rejected.
CORS_ORIGINS=https://app.yourdomain.com    # must name the real frontend origin
SECURE_COOKIES=true
CSRF_ENABLED=true
METRICS_ENABLED=true
METRICS_TOKEN=<token>                      # required to read /metrics in production

# --- Rate limits (per-key, e.g. "60/minute") ---
RATE_LIMIT_DEFAULT=300/minute
RATE_LIMIT_AUTH=300/minute
RATE_LIMIT_TRANSLATE=60/minute
RATE_LIMIT_WS_CONNECT=30/minute
```

`render.yaml` generates `SECRET_KEY` and `JWT_SECRET` and marks `DATABASE_URL` and
the four `SUPABASE_*` keys `sync: false`, meaning they are **not** copied between
services — set them on each service by hand and confirm by name, never by value.
Do not print secret values into logs, tickets, screenshots, or the verification
report; report a missing or misconfigured variable by name only.

---

## 3. Deployment & Rollout Procedures

### 3.1 Zero-Downtime Migration & Rollout Sequence
1. **Pre-Deployment Database Migration** — Tree A's Alembic environment lives in
   `services/api` (`alembic.ini` + `alembic/versions`), so run it from there:
   ```bash
   cd services/api && alembic upgrade head          # against DATABASE_URL
   alembic current                                  # must print the release's head
   ```
   `start.sh` does `alembic upgrade head` on every boot, so the step above is the
   *pre-flight* check that the migration is safe, not the only place it runs.
   Container route: `docker-compose run --rm api alembic upgrade head`.
2. **Container Image Build & Verification**:
   ```bash
   docker build -t globaltalk/api:release-v1.0.0 -f infrastructure/docker/Dockerfile.api .
   docker build -t globaltalk/web:release-v1.0.0 -f apps/web/Dockerfile apps/web
   ```
3. **Rolling Update via Kubernetes or Docker Compose**:
   ```bash
   kubectl set image deployment/globaltalk-api api=globaltalk/api:release-v1.0.0
   kubectl rollout status deployment/globaltalk-api
   ```
4. **Post-Deployment Health Probe**:
   ```bash
   curl -f http://localhost:8088/health
   curl -f http://localhost:8088/ready || exit 1   # 503 if DB/cache/queue/storage not ready
   curl -fs 'http://localhost:8088/version' | python -m json.tool   # see 3.2
   ```

### 3.2 What "/deployed" actually means today

The running deployment is **not** the Docker/Kubernetes route above. It is:

| Piece | Where it runs | Source tree |
|---|---|---|
| API | Render web service `globaltalk-api` (`rootDir: services/api`, `startCommand: bash start.sh`, health check `/health`, `autoDeploy` on `main`) | **Tree A** — `services/api/app.*` |
| Frontend | Vercel | `apps/web` (Vite) |
| Cache | Render key-value/Redis `globaltalk-cache` | — |

`infrastructure/docker/Dockerfile.api`, the Kubernetes commands, and
`GET /internal/components` describe **Tree B** (`apps/api/globaltalk.*`, port 8000),
which is the legacy golden-test tree and is not what Render serves. Do not use
`/internal/components` to judge a production instance — it 404s on Tree A. Use
`GET /version`, whose `ai` object reports, per task, both the configured provider
and whether this image can actually run it (`importable` / `missing` / `remote` /
`remote_unconfigured` / `dev_stand_in`).

**Why that check matters:** `provider` alone is not evidence. `auto` resolves to the
head of a preference list, so a build that installs no speech runtime still
advertised `faster_whisper` while every call silently fell through to the dev
stand-in. `importable` only means the package is in the image — weights, voice
files, API keys and a loadable runtime are proven only when a stage runs, which is
what `realtime/health` (§5) and the `gt_*_failures_total` counters show.

### 3.3 Staging → verify → rollback (the path the release gate requires)

Never promote straight to the production service. Sequence:

1. **Deploy to a staging Render service first.** Create a second Render web service
   from `render.yaml` pointed at the release branch, on its own database. (A
   staging instance is a paid resource — it needs an explicit owner decision.)
2. **Boot must pass the migration gate.** `services/api/start.sh` runs
   `alembic upgrade head` and then starts uvicorn. In production,
   `app/main.py:_ensure_schema()` **fails closed**: it refuses to boot unless
   `alembic_version` equals the expected head
   (`EXPECTED_HEAD = "2202ca7dc080"`). A crash-loop with
   `Database migration version mismatch in production` is the gate working, not a
   bug to switch off.
3. **Verify configuration, by name only — never print values:**
   ```bash
   curl -fs https://<staging>/health
   curl -fs https://<staging>/ready          # checks database, cache, queue, storage
   curl -fs https://<staging>/version        # env, protocol_version, ai runtime report
   ```
   Confirm every `*_PROVIDER` resolves to an engine rather than `dev_*`, that
   `CORS_ORIGINS` names the real frontend origin, that `METRICS_ENABLED`/
   `METRICS_TOKEN` are as intended, and that `DATABASE_URL` points at the staging
   database. Report a missing variable by its name; do not echo secrets into logs,
   tickets, or this report.
4. **Run one real two-browser call on staging** and read
   `GET /api/v1/meetings/{id}/realtime/health` afterwards. Record the `gt_e2e_latency_ms`
   p50/p95 and any `gt_translation_failures_total` / `gt_stale_audio_dropped_total` /
   `gt_ws_send_dropped_total` movement. Attach that to the verification report.
5. **Only then** merge to `main` (Render auto-deploys `main`) and repeat step 3
   against production.

---

## 4. Emergency Procedures & Rollback

**The rule that governs all of this: never remove the working baseline as a
shortcut.** Roll the app back to the last known-good release; do not delete or
disable the feature area that is failing in order to make the dashboard green.
Keep the feature branch isolated until it has passed staging.

### 4.1 Render + Vercel (what is deployed today)

```bash
# API — Render: revert to the previous successful build
git revert <sha> && git push origin main     # preferred: a forward revert, keeps history
# or in the dashboard: Services → globaltalk-api → Images → pull the last good commit
#                      and "Manual Deploy" on that commit.

# Frontend — Vercel: Projects → globaltalk-web → Deployments → Promote ⋯ → Rollback
```

`autoDeploy` is on for `main`, so a `git push` to `main` is a production deploy.
Reverting a merge commit needs `git revert -m 1 <merge-sha>`.

**The app must not outrun the schema.** `start.sh` applies migrations on boot, and
production refuses to start unless `alembic_version` is the revision that release
expects. So rolling the *app* back to an older release while the database stays at
the newer head produces a crash loop, not a rollback. Order of operations:

1. Check whether the release included a migration (`git diff <good>..<bad> -- services/api/alembic/versions`).
2. If it did **and** the migration is additive (new nullable column, new table),
   the older app usually still boots — try the app revert first and confirm `/ready`.
3. If it did **and** the migration is destructive (dropped/renamed column, changed
   constraint, backfilled data), you must roll the schema back with the app:
   `alembic downgrade -1` against the Render database, then deploy the older app.
   Take a backup first (§4.3). Never run `downgrade` blind on production data —
   prefer restoring from the snapshot.
4. If neither works, redeploy the last good image with the schema it expects, in
   this order: restore snapshot → deploy app → `/ready` → one real two-browser call.

### 4.2 Kubernetes / Docker Compose (Tree B, not currently deployed)

**Application rollback:**
```bash
# Kubernetes rollback
kubectl rollout undo deployment/globaltalk-api
kubectl rollout status deployment/globaltalk-api

# Docker compose rollback
docker-compose down
git checkout <previous-tag>
docker-compose up -d
```

**Schema rollback** — if a migration introduced unexpected constraints:
```bash
alembic downgrade -1
```

### 4.3 Database Backup & Restore
```bash
# Backup
pg_dump -U postgres -d globaltalk -F c -b -v -f /backups/globaltalk_$(date +%Y%m%d_%H%M%S).dump

# Restore
pg_restore -U postgres -d globaltalk -v -c /backups/globaltalk_20261004.dump
```

---

## 5. Monitoring, Metrics & Observability

- **Prometheus Metrics Endpoint**: `GET /metrics`
  Returns 404 unless `METRICS_ENABLED=true`. In production with `METRICS_TOKEN`
  set, it requires `Authorization: Bearer <METRICS_TOKEN>` (or `X-Metrics-Token`).
- **Stage-level health (per meeting)**: `GET /api/v1/meetings/{meeting_id}/realtime/health`
  Requires an org user with `view_usage`. Answers for the four stages
  `listening → translation → voice → delivery`, each with a `status`, `pending_ms`
  and the events that produced it. Statuses outside `ok`, `not_yet_ran`,
  `not_expected` (`degraded`, `waiting`, `failed`, `dev_stand_in`) are the thing to
  page on. `dev_stand_in` is deliberately not treated as healthy: the path ran, but
  on a dev stand-in instead of an engine, which is exactly what a deployment must
  see rather than sail past as green.
  **Caveat:** the pipeline lives in the worker that holds the room's WebSocket.
  A request routed to any other worker returns
  `{"live": false, "stages": {}, "healthy": true, "reason": "no session in this process"}`.
  That response is not evidence of health — with more than one replica, pin the
  room's websocket and this probe to the same instance (sticky routing) or check
  per-replica.
- **Key Metrics to Alert On** (these are the actual `gt_*` names exposed by
  `services/api/app/metrics.py`; the earlier version of this section listed names
  the code never emitted):

| Metric | Type | Labels | Alert on |
|---|---|---|---|
| `gt_e2e_latency_ms` | Histogram | `src`, `tgt` | p95 above 2500 ms (see §5.1) |
| `gt_translation_latency_ms` | Histogram | `src`, `tgt`, `provider` | p95 regression per provider |
| `gt_stt_latency_ms` | Histogram | `provider` | p95 regression |
| `gt_tts_first_audio_ms` | Histogram | `provider` | p95 above ~1000 ms |
| `gt_translation_failures_total` | Counter | `src`, `tgt`, `provider`, `reason` | any sustained rate; `reason=provider_cooldown` means the breaker opened |
| `gt_stale_audio_dropped_total` | Counter | `reason` | rising: late audio is being discarded |
| `gt_ws_connections_active` | Gauge | — | drop unrelated to meeting ends |
| `gt_ws_reconnects_total` | Counter | — | sustained reconnect storms (proxy/idle timeout) |
| `gt_ws_send_dropped_total` | Counter | `kind`, `reason` | any increase: a listener's bounded outbound queue overflowed |
| `gt_active_meetings` / `gt_active_participants` | Gauge | — | capacity planning |
| `gt_queue_depth` / `gt_queue_dlq_depth` | Gauge | `queue` | DLQ non-zero is an incident, not a warning |
| `gt_job_executions_total` | Counter | `queue`, `type`, `status` | `status=failed` rate |
| `gt_cache_operations_total` | Counter | `op`, `status` | `status=error` (Redis degradation) |
| `gt_auth_events_total` | Counter | `event`, `status` | spike in `status=failure` |
| `gt_security_violations_total` | Counter | `type` | any non-zero |
| `gt_gpu_utilization` | Gauge | — | saturation if inference is self-hosted |
| `gt_usage_characters_total` / `gt_usage_audio_seconds_total` | Counter | `product` / — | cost tracking |
| `gt_http_requests_total` / `gt_http_request_duration_seconds` | Counter / Histogram | `method`, `path`, `status` | 5xx ratio |

### 5.1 The latency target is a measurement, not a promise

The 1.5 s median / 2.5 s p95 first-translated-audio goal is a goal to measure. The
only baseline recorded so far (`docs/REALTIME.md`, 2026-10-13, `hi→en`, 20 turns,
dev STT/TTS stand-ins over a live internet machine-translation path, loopback) is
**p50 1429 ms / p95 2217 ms**. It says nothing about real-provider behaviour, real
networks, or real microphones, and must not be quoted as a shipped guarantee.
Publish numbers only with the provider set, direction, sample count and environment
that produced them.

---

## 6. Incident Troubleshooting Guide

### 6.1 Realtime Audio / WebSockets Failing
1. Check ticket generation: `POST /api/v1/meetings/{id}/tokens` (requires an
   authenticated org user who has already joined) returns
   `{ticket, ws_url: "/ws/realtime?ticket=…", participant_id}`. Guests join with
   `POST /api/v1/meetings/{id}/join` and connect with `?join_token=guest-…`.
2. Check reverse proxy WebSocket upgrade: ensure the proxy passes `Upgrade` and
   `Connection` headers and does not idle-close the socket. Look for
   `gt_ws_reconnects_total` growth.
3. Check Redis PubSub: if the API runs multi-instance, verify Redis is reachable
   (`/ready` reports `cache` and `queue`). Multi-instance fanout across workers is
   **not** proven by the tests in this repo — treat it as unverified and prefer one
   replica per room until it is.
4. **"Translation Unavailable · no_targets" on the speaker's screen with no caption
   delivered to anyone.** This is observed when a turn goes up while the room holds
   only one participant — the second seat's join handshake had not finished yet, so
   the turn has no one to fan out to. It is a timing race at meeting start, not a
   provider outage. Ask the reporter whether the listener's
   "Connected · Realtime Translation Active" pill had appeared before they spoke.
5. **Silent fallback to the dev stand-in in production.** `GET /version` shows
   `provider` plus `runtime`; `dev_stand_in` anywhere means real speech is being
   answered by a fixture. Check `STT_PROVIDER` / `TRANSLATION_PROVIDER` /
   `TTS_PROVIDER` (by name — do not log their outputs) and whether the runtime
   package and model weights are present in the image.

### 6.2 Translations Falling Back to Untranslated Text
1. Query the capability registry: `GET /api/v1/languages` to check whether the
   target language is advertised as supported at all.
2. Inspect what the image can run: `GET /version` → `ai` (see 6.1.5).
   `/internal/components` is Tree B only and 404s on the deployed service.
3. Inspect what the room actually did: `GET /api/v1/meetings/{id}/realtime/health`
   → the `translation` and `voice` stage statuses and their events.
4. Check the breaker: `gt_translation_failures_total{reason="provider_cooldown"}`
   rising means the provider tripped the circuit (4 failures → 30 s cooldown,
   doubling up to 600 s; see `docs/REALTIME.md`). Recovery is half-open probes, not
   a restart.
5. Check worker memory: model inference needs headroom, and a killed worker looks
   like a provider timeout from the outside.

### 6.3 Boot crash-loops with a migration error
`Database migration version mismatch in production: found '<rev>', expected
'2202ca7dc080'` is the fail-closed schema gate in `app/main.py`. Fix forward with
`alembic upgrade head` against that database. Do **not** edit `EXPECTED_HEAD` or
force the app to boot against a schema it does not recognise to stop the crash loop
— that turns a visible outage into silent data corruption. If the release is being
rolled back instead, follow §4.1.
