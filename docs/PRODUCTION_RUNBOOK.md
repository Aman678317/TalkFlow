# TalkFlow / GlobalTalk AI — Production Runbook & Operations Guide

**Audience**: DevOps Engineers, SREs, Systems Administrators  
**Stack**: FastAPI (Python 3.11+ / 3.14), React 18 / Vite, PostgreSQL, Redis, LiveKit SFU, Docker / Kubernetes

---

## 1. System Architecture & Component Ports

| Component | Container Name | Production Port | Health Endpoint |
|---|---|---|---|
| **API Gateway / Core Service** | `globaltalk-api` | `8088` (or `8000`) | `GET /ready` & `GET /health` |
| **Frontend Web App** | `globaltalk-web` | `80` / `443` | `GET /` |
| **Database** | `globaltalk-db` | `5432` (PostgreSQL) | `pg_isready` |
| **Cache & Realtime Queues** | `globaltalk-redis` | `6379` (Redis) | `PING` |
| **LiveKit SFU** | `globaltalk-livekit` | `7880` (HTTP) / `7881` (TCP) / `7882` (UDP) | `GET /` |

---

## 2. Environment Variables & Secrets Reference

### 2.1 Critical Production Configuration
```bash
# --- Core Environment ---
APP_ENV=production
LOG_LEVEL=INFO
SECRET_KEY=<32-character-random-hex-string>
JWT_SECRET=<32-character-random-hex-string>
JWT_ALGORITHM=HS256
JWT_ACCESS_TTL_MINUTES=30
JWT_REFRESH_TTL_DAYS=30

# --- Datastores ---
DATABASE_URL=postgresql+asyncpg://postgres:secure_password@postgres:5432/globaltalk
GLOBALTALK_DATABASE_URL=postgresql://postgres:secure_password@postgres:5432/globaltalk
REDIS_URL=redis://:redis_password@redis:6379/0
CACHE_BACKEND=redis

# --- Storage ---
S3_ENABLED=true
S3_ENDPOINT=https://s3.amazonaws.com
S3_BUCKET=globaltalk-production-storage
S3_ACCESS_KEY_ID=<aws_key_id>
S3_SECRET_ACCESS_KEY=<aws_secret_key>
S3_REGION=us-east-1

# --- Realtime Transport (LiveKit) ---
LIVEKIT_ENABLED=true
LIVEKIT_URL=wss://livekit.yourdomain.com
LIVEKIT_API_KEY=<lk_api_key>
LIVEKIT_API_SECRET=<lk_api_secret>

# --- Security Controls ---
MALWARE_SCAN_ENABLED=true
CLAMAV_HOST=clamav
CLAMAV_PORT=3310
CORS_ORIGINS=https://app.yourdomain.com
SECURE_COOKIES=true
CSRF_ENABLED=true
```

---

## 3. Deployment & Rollout Procedures

### 3.1 Zero-Downtime Migration & Rollout Sequence
1. **Pre-Deployment Database Migration**:
   ```bash
   # Run migration before updating application containers
   docker-compose run --rm api alembic upgrade head
   ```
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
   curl -f http://localhost:8088/ready || exit 1
   curl -f http://localhost:8088/internal/components || exit 1
   ```

---

## 4. Emergency Procedures & Rollback

### 4.1 Application Rollback
If application health checks fail post-deployment:
```bash
# Kubernetes rollback
kubectl rollout undo deployment/globaltalk-api
kubectl rollout status deployment/globaltalk-api

# Docker compose rollback
docker-compose down
git checkout <previous-tag>
docker-compose up -d
```

### 4.2 Database Rollback
If a migration introduces unexpected constraints:
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
- **Key Metrics to Alert On**:
  - `translation_requests_total`: Request volume.
  - `translation_latency_seconds_bucket`: Latency percentiles (P50, P95, P99).
  - `translation_failures_total`: Spikes in MT or STT degradation.
  - `active_websocket_connections`: Active concurrent meeting participants.
  - `worker_queue_depth`: Unprocessed document translation jobs.
  - `database_pool_in_use`: Database connection pool saturation.

---

## 6. Incident Troubleshooting Guide

### 6.1 Realtime Audio / WebSockets Failing
1. Check ticket generation: Verify `POST /api/v1/meetings/{id}/tokens` returns a valid ticket.
2. Check reverse proxy WebSocket upgrade: Ensure NGINX or Traefik passes `Upgrade` and `Connection` headers.
3. Check Redis PubSub: If multi-instance API is running, verify Redis is reachable via `redis-cli ping`.

### 6.2 Translations Falling Back to Untranslated Text
1. Query capability registry: `GET /api/v1/languages` to verify target language is marked `SUPPORTED` or `PRODUCTION`.
2. Inspect component health: `GET /internal/components` to check if `argos-translate` or `faster-whisper` reports `FAILED`.
3. Check worker memory: Ensure host has sufficient RAM for model inference.
