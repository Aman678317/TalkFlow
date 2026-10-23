# Recovery Runbook (30-DAY-ROADMAP §Day 5)

Status (2026-10-23): **drill executed this day on every stateful surface** — source-of-truth
map fixed below, isolated-restore procedures proven live (§2), repeatable SQLite audit asset
shipped (`scripts/drill_backup_restore_sqlite.py`). Production-true RTO/RPO numbers and the
runbook's owner approval are RECORDED owner items (§5) — code-side Day-5 scope is exhausted,
nothing here is waved away.

## 1. Source-of-truth map (durable vs recoverable)

| Store | Backing | Durable content | Loss behaviour | Recovery path |
|---|---|---|---|---|
| Application database | **PostgreSQL 16** in production (managed, e.g. Render); SQLite in dev/test lanes | **The source of truth**: users/orgs/memberships, contacts/consents/campaigns/call jobs, meetings/transcripts, documents metadata, `agent_escalations`, `alembic_version` | Full data loss if destroyed | Backup/restore drills in §2–§3; restore **only** into a fresh isolated instance, verify, then repoint `DATABASE_URL` |
| Object storage | prod: S3-compatible bucket (owner-managed); local lane: `local_storage_path` (default `./data/storage`) | Uploaded document bytes (files, audio) — DB rows hold the object *keys* | Upload/preview surfaces break on 404s | Mirror/snapshot + restore + byte-hash verify (§3.3); keys are deterministic (`object_key(kind, tenant, name, checksum)`) |
| Redis | `REDIS_URL` (required by config for production) | **Nothing durable by design**: cache-aside entries (rate limits, caches) + transit job state (`gt:queue:*` active/processing/delayed/dlq) | `_r.FLUSHDB` is safe — cold cache, empty queue | Rebuild = let caches repopulate; re-enqueue lost jobs from DB state via `POST /documents/{id}/retry`, `RedisQueue.sweep_stale_processing`, `RedisQueue.reprocess_dlq` (§3.4); rate limiting fails **open** under a dead cache (pinned: `tests/integration/test_resilience_failures.py`) |
| Model weights cache | `MODEL_CACHE_PATH` volume | Downloaded model artifacts | Re-downloadable; never user data | `scripts/download_models.sh` (pinned) |
| Queue source-of-truth | PostgreSQL | Every enqueueable work item exists as a DB row first (documents, call jobs, escalations) | Redis flush never corrupts DB data | Retry/re-enqueue from rows (§3.4); escalations persist in `agent_escalations` (DB-backed `DBEscalationStore`, not redis) |

## 2. Day-5 drill evidence (2026-10-23, local, isolated from all product data)

### 2.1 SQLite lane (repeatable asset)
`python scripts/drill_backup_restore_sqlite.py` — creates its own throwaway origin DB in an
isolated temp dir, migrates to head, seeds a tenant, snapshots via SQLite's online backup API,
**deletes the origin**, restores into a second isolated dir, verifies. Result: **PASS**
(migrate 4.81 s; seed 1/1/1; backup 0.017 s, sha256 recorded; origin deleted; restore 0.004 s
byte-identical to backup; verify: `integrity_check=ok`, 0 FK violations, logical dump digest
of restored == origin (`389b1ba1…`), `alembic current` = `f4e2a9c1d8b7 (head)`, `alembic check`
= clean. Restore→verified 4.14 s; full drill 9.03 s.)

Honest note: two red runs preceded the green one — a wrong seed column and a Windows file-lock
leak — both fixed in the script; the drill reports failures as data (`result=FAIL` + stage) and
never masks them.

### 2.2 PostgreSQL lane (live, isolated restore target)
Source: compose `postgres:16` container, migrated with the repo's migrations to
`f4e2a9c1d8b7`, seeded a tenant (org/user/membership). Then:

| Step | Result |
|---|---|
| `pg_dump -U globaltalk -F c -d globaltalk -f /tmp/...dump` **inside the container** | 0.355 s, 148 238 bytes |
| sha256 across container→host→restore-target boundaries | identical: `44899c71d135db02119c6b8974130343ce6388695ede3dcdc76516040becbd45` |
| Isolated target: fresh `postgres:16` container, **new volume**, port 5433 | healthy |
| `CREATE DATABASE day5_restored` (0.336 s) + `pg_restore -U postgres -d day5_restored --no-owner` | 1.615 s, **rc=0** |
| Verify restored: `alembic_version` | `f4e2a9c1d8b7` (head) |
| Row round-trip (`organizations`/`users`/`organization_members`) | 1 / 1 / 1 |
| `alembic current` against restored DB | `f4e2a9c1d8b7 (head)` |
| `alembic check` against restored DB | **rc=0 — "No new upgrade operations detected."** (migration-compatible) |

Restore→verified ≈ 2.0 s at drill scale. (PowerShell stdout-encoding caveat honored: the dump
never travels through a redirected native-command pipe — it is written inside the container and
`docker cp`'d out, then hash-compared in-container and on the host.)

### 2.3 Redis rebuild (live)
`redis-cli SET gt:day5demo … → DBSIZE=1 → FLUSHALL → PING=PONG → DBSIZE=0` — server healthy
post-flush, state discarded cleanly; compose runs `--appendonly yes` (appendonlydir present,
nothing durable rides in it). Cache is additive-only: the rate limiter fails **open** on cache
outage — pinned by `tests/integration/test_resilience_failures.py`; the queue holds transit
state only (`gt:queue:*`), with at-least-once processing, DLQ replay, and stale-claim sweep
(`services/api/app/queue.py`).

### 2.4 Object storage — local lane (app-backend round trip)
Three objects written through the app's own `LocalStorage.put`, directory mirror-snapshotted,
**directory destroyed**, restored, and re-fetched through the same backend — all three
byte-hash matched (`doc/org-drill/…/brief-{0,1,2}.md`; restore→verified 0.017 s). The S3/MinIO
lane follows the same mirror + hash pattern (§3.3) — the bucket drill is an owner item §5
(the repo's own compose documents that `minio/minio` is no longer anonymously pullable from
Docker Hub, so the MinIO-local lane was not exercised here).

## 3. Recovery procedures

### 3.1 PostgreSQL (production / staging — owner-executed)
```bash
# Always dump INSIDE the server/container and copy out (never redirect binary
# dump bytes through a shell pipe):
pg_dump -U <user> -d globaltalk -F c -f /tmp/globaltalk_<ts>.dump
# copy /tmp/globaltalk_<ts>.dump off the server into immutable backup storage; record sha256.

# RESTORE — never over the live instance. Fresh isolated instance first:
createdb -U postgres day5_restored
pg_restore -U postgres -d day5_restored --no-owner /baseups/globaltalk_<ts>.dump

# VERIFY before repointing DATABASE_URL:
alembic current          # must equal the head revision the app expects
alembic check            # must exit 0 (drift clean)
# row-count spot checks on the largest tables + a login smoke against the restored URL.
# Only then repoint DATABASE_URL; keep the old instance until verification passes.
```
Policy target (`docs/DEPLOYMENT.md`): nightly base backups + continuous WAL archiving; restore
drill quarterly. The quarterly drill = §2.2's sequence against the provider's dump.

### 3.2 Local SQLite lane (dev/test)
```bash
python scripts/drill_backup_restore_sqlite.py            # isolated throwaway dirs, JSON report
python scripts/drill_backup_restore_sqlite.py --keep     # keep dirs for post-mortem
```
Runbook rule: never back up a running API's SQLite file with a raw file copy — use SQLite's
online backup API (what the script does) or stop the server first.

### 3.3 Object storage
- Local lane: mirror `local_storage_path` (rsync/cp -r to immutable storage + sha256 manifest;
  restore = copy back; verify with `LocalStorage.get` byte hashes). Pin manifests alongside the
  backup.
- S3/MinIO lane (owner, with real credentials): `mc mirror globaltalk/ /backup/globaltalk/`
  (or provider-versioning + cross-region replication per `docs/DEPLOYMENT.md`); restore into a
  NEW bucket/prefix first, hash-compare against the manifest, then repoint. Keys are
  deterministic and tenant-prefixed — a mismatched key is safe to reject rather than merge.

### 3.4 Redis & queues (safe rebuild)
```bash
redis-cli -u $REDIS_URL FLUSHDB   # safe: no durable state by design
```
Lost in-flight work is re-derived from the database, never reconstructed from Redis:
1. documents left `pending` → `POST /documents/{id}/retry` (re-enqueues `document.process`),
2. unacked jobs from a crashed worker → `RedisQueue.sweep_stale_processing(queue)`,
3. dead-lettered jobs → `RedisQueue.reprocess_dlq(queue)`.

## 4. Verification matrix (what pins these guarantees)

| Guarantee | Pinned by |
|---|---|
| Rate limiting / caches never corrupt on store loss | `tests/integration/test_resilience_failures.py` (fail-open on cache outage) |
| Processing queue never fabricates or loses committed state | `queue.py` at-least-once + DLQ replay + stale sweep; `POST /documents/{id}/retry` |
| Schema always restorable, migrations compatible after restore | `alembic check` in CI (must exit 0) + §2.2 restored-DB check |
| Escalation data durable | `agent_escalations` table via `DBEscalationStore` (DB-backed, redis-independent) |
| Upload integrity on the write path | `validate_upload` + `malware_scan` (`storage.py`, pinned in `tests/test_storage_webhooks.py`) |

## 5. RECORDED owner items (documented exclusions — nothing open in code)

| Item | Why it is owner-side |
|---|---|
| **Owner approval of this runbook** (the §Day-5 exit criterion) | requires the accountable owner's sign-off |
| First production/staging backup execution + **real RTO/RPO numbers** | needs Render/production credentials; §2 timings are drill-scale, not production claims |
| Postgres backup schedule confirmation (nightly base + WAL archiving) | managed-provider configuration lives in the owner's account |
| S3/MinIO object-storage backup policy (versioning/CRR) execution | owner-managed bucket; MinIO image not anonymously pullable (compose documents this) |
| MinIO-local drill lane (once a pullable image or registry is available) | blocked by the anonymous-pull caveat above |
