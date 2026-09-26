# Deployment

## Docker Compose (single host)

```bash
docker compose -f infrastructure/docker/docker-compose.yml up --build
# web  → http://localhost:8080   api → http://localhost:8000/docs
# postgres(pgvector) · redis · minio · livekit · api · worker · web · prometheus · grafana
# GPU inference worker:  --profile gpu   (NVIDIA container toolkit required)
docker compose -f infrastructure/docker/docker-compose.yml down
```

The api container runs `alembic upgrade head` before serving (migration job inline;
on k8s it's a separate Job).

## Kubernetes

`infrastructure/kubernetes/globaltalk.yaml`: namespace, Secret/ConfigMap (replace with
External Secrets/Vault), model-cache PVC (RWX), migrate Job, api Deployment (3 replicas,
readiness `/ready`, liveness `/health`, Prometheus annotations) + HPA (CPU 65%, 3→30),
worker Deployment (queue drain), inference-gpu Deployment (nvidia.com/gpu, nodeSelector
`globaltalk.ai/gpu`), web Deployment + Services, nginx Ingress with cert-manager TLS and
WebSocket timeouts (3600 s).

Scaling rules (section 58): API scales on CPU/connections; workers on queue depth
(KEDA on Redis list length recommended); inference on GPU utilization; LiveKit via its
own autoscaling. Never run heavy inference inside API pods — the queue boundary enforces it.

## Backups & DR

- Postgres: continuous WAL archiving + nightly base backups; restore drill quarterly.
- Object storage: versioning + cross-region replication for prod buckets.
- Model weights: reproducible via `scripts/download_models.sh` (pinned); cache PVC is
  disposable.
- Redis: cache/queue only — loss degrades to in-process mode, no source-of-truth data.

## Health semantics

`/health` = process alive (always 200 when serving). `/ready` = 200 only when required
dependencies answer (DB, storage, LiveKit *if configured*); cache degradation is reported
but tolerated (in-process fallback). Orchestrators must use `/ready` for traffic.

## TLS / reverse proxy

nginx conf (infrastructure/docker/nginx.conf) proxies /api, /ws (upgrade-aware), /docs,
/metrics, /internal and serves the SPA with security headers. In k8s the Ingress handles
termination; set `X-Forwarded-Proto` and trust proxy headers for audit IPs.

## Environments

`.env.example` (reference) · `.env.development` · `.env.test` · `.env.production.example`
(copy → fill secrets; never commit real values). Feature flags ship dark
(`agent_bridge`, `voice_preservation`, `enterprise_sso`, `seamless_research` off).

## Release process

CI (GitHub Actions): backend tests (SQLite + Postgres/pgvector/Redis lanes), realtime
golden call with downloaded weights, frontend typecheck/vitest/build, docker image builds.
Images tagged by git SHA; k8s rollout via migrate Job → api → workers. Rollback = previous
tag (migrations are additive; expand/contract discipline).
