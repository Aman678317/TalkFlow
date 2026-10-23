# TalkFlow / GlobalTalk AI — Staging rehearsal record (Day-2 / remediation R2)

**Date:** 2026-10-23 · **Scope:** `docs/POST-COMPLETION-30-DAY-LAUNCH-ROADMAP.md` §Day 2 and
`docs/GO_NO_GO_CHECKPOINT.md` §8 **R2** · **Decision owner:** owner + dev (this record covers the dev half).

**Verdict:** the R2 evidence list is **satisfied on an isolated, production-mode staging-like stack** —
health, readiness, migrations, worker connectivity, secrets injection and API/worker restart-recovery are all
saved with live evidence (all 15 drill steps PASS, clean run + teardown). This is **not** a hosted staging
deployment: TLS/WSS and the deferred launch sign-off browser round remain recorded open items (§8), not waived.

## 1. Candidate and images under test

| Item | Value |
|---|---|
| Candidate | `launch-candidate-1` tag @ `45c15b9`; runtime images were built from the same tree content (the only later commit, `ffec843`, is the docs-only R1 record) |
| API image (local build) | `tts-staging-drill-api:latest` — `sha256:6cef510154cce17619167ad4a4cd443e6ab442a600e66881bb1ce90c02351eae` |
| Worker image (local build) | `tts-staging-drill-worker:latest` — `sha256:71bf6ec4822294b9ea169316b20ebc8bab2998b9ffb6fb8400f4d520df8e150a` |
| Infra | `postgres:16` · `redis:7-alpine` · MinIO `2024.6.13` (`bitnamilegacy/minio@sha256:aa1752895e6d2b420e394d55241d5b2c948960715db0a50bb648f430e447e645`) · `livekit/livekit-server:v1.13.10` (`sha256:89ca9ce0…`) |
| Compose project | `tts-staging-drill` — isolated project name; never the canonical `globaltalk-ai` stack |
| Overlay | `docker-compose.staging-rehearse.yml` (host ports remapped to 5xxxx; production-shaped in-network ports) |
| Drill driver | `scripts/drill_staging_rehearsal.py` |

## 2. Environment truth

`APP_ENV=production` (API refused to boot otherwise — the production config gates are fail-closed):

- `DATABASE_URL=postgresql+asyncpg://…@postgres:5432/globaltalk` (non-SQLite, PostgreSQL 16)
- `REDIS_URL=redis://redis:6379/0`, `CACHE_BACKEND=redis`
- `S3_ENABLED=true`, `S3_ENDPOINT=http://minio:9000` (bucket `globaltalk` created by `minio-init`)
- `CORS_ORIGINS=http://localhost:5173` (exact origin, no wildcard)
- `METRICS_ENABLED=true`, token-protected (`/metrics`: bare GET **401**, bearer token **200**)
- `TELEPHONY_PROVIDER=simulated`
- `LIVEKIT_ENABLED=false` — recorded exclusion: this box has no TLS-terminating browser endpoint, so the
  production `wss://` rule cannot be met truthfully. The LiveKit container is present (healthy) for infra
  parity only; the browser/WebRTC path stays CI-verified in `webrtc-smoke`.
- Secrets injected as rehearsal-only dummies; in-container probe: `production 55 54 48 True` — i.e.
  `SECRET_KEY`/`JWT_SECRET`/`METRICS_TOKEN` lengths 55/54/48 and `secure_cookies=True`.

Migrations were pre-applied the production way before app boot (production boot refuses an uninitialized
schema): `alembic upgrade head` → `alembic current` = `f4e2a9c1d8b7 (head)`, `alembic check` = "No new
upgrade operations detected."

## 3. Clean-run evidence (2026-10-23 15:12:33 → 15:13:37 +0530)

| Step | Result | Evidence |
|---|---|---|
| Infra up (postgres, redis, minio, minio-init, livekit) | PASS, 10.51 s | `docker_ps_after_infra.txt` |
| Infra healthy poll (pg_isready, Redis PING) | PASS, 1.01 s | `infra_probe.txt` |
| Migrations upgrade head | PASS, 5.70 s | `alembic_upgrade.log` |
| Migrations current + check | PASS, 9.59 s | `alembic_current_check.txt` |
| API + worker boot in production mode | PASS, 13.01 s | container state |
| `/health` | 200, 0.30 s (uptime 7.4 s) | `health_first.json` |
| `/ready` | 200 — `database`, `cache`, `queue`, `storage` all true | `ready_first.json` |
| Worker connectivity | PASS — `document worker started (queue=documents)`, `job queue: redis`, `storage backend: s3` | `worker_log_tail.txt` |
| `/metrics` access truth | bare 401 / bearer 200 | `metrics_probe.txt` |
| Signup → login | 201 / 200 (token present) | `signup.json`, `login.json` |
| Meeting create + fetch | 200 / 200, same id | `meeting_created.json`, `meeting_fetched.json` |
| API restart-recovery | PASS, 11.15 s total — `/health` 200 in 6.1 s, `/ready` 200 in 0.1 s, re-login 200, **meeting row survives**, Redis `DBSIZE=2` (transient only) | `restart_recovery.json` |
| Worker restart | PASS, 10.47 s — queue consumer ribbon again after restart | `worker_log_after_restart.txt` |
| Secrets-injection probe | PASS — `production 55 54 48 True` | `secret_probe.txt` |
| Teardown (`down -v`, drill project only) | PASS, 8.57 s — zero residual containers/volumes | `drill_teardown.log` |

All 15 steps PASS in the clean run; total drill wall time ≈ 64 s. Timings are **drill-scale**, not
production RTO/RPO claims. The canonical `globaltalk-ai` compose project was already stopped before the
drill and was untouched by it (verified before and after).

## 4. Tooling corrections made while executing R2

- `scripts/drill_staging_rehearsal.py` teardown sliced `stdout`/`stderr` without capture → `'NoneType' object
  is not subscriptable`; fixed with `capture=True`.
- The worker assertion expected the `app/workers_runner.py` banner. That module is the documented orphan
  (`docs/ARCHITECTURE_OWNERSHIP.md` O-6) and is **not** what the worker image runs; the drill now asserts the
  deployed `WORKER_KIND` entrypoint (`document worker started (queue=documents)` + `job queue: redis`).
- Upstream removed the `minio/minio` Docker Hub repository, so the base-compose MinIO tag cannot be pulled.
  The rehearsal-only overlay therefore uses the Bitnami legacy mirror of the same MinIO 2024.6.13 server,
  pinned by digest; the base `docker-compose.yml` is unchanged.

## 5. Reproduce

```bash
# from the repo root (Docker Desktop running)
docker compose -p tts-staging-drill -f docker-compose.yml -f docker-compose.staging-rehearse.yml \
  build api worker
python scripts/drill_staging_rehearsal.py           # clean run
python scripts/drill_staging_rehearsal.py --teardown
```

Artifacts: `%TEMP%\opencode\day2\staging\` (`drill_summary.full.json` is the preserved clean-run summary;
the later teardown run rewrites `drill_summary.txt` with its own single-step record).

## 6. Exclusions and residual open items (recorded, not waived)

1. **No TLS/WSS staging and no hosted/cloud staging** — this is a single-host, production-mode local
   rehearsal. A hosted staging deployment with real TLS remains open.
2. **Deferred launch sign-off browser round** still not executed (this rehearsal unblocks it; it does not
   replace it).
3. **LiveKit/WebRTC** was infra-only (`LIVEKIT_ENABLED=false`); no browser media was exercised here.
4. **Drill-scale timings** — not production RTO/RPO and not load/latency claims (Day 6 owns those).
5. **First staging backup execution** remains tied to R8 (Day 5 owner item).
