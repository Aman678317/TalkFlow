---
name: health-check
description: "Post-deployment health verification and synthetic probing. Validates uptime, component dependencies (DB, Redis, AI model providers, WebRTC signaling), and latency budgets."
---

# Post-Deployment Health Verification Mode

Verify live production systems using synthetic probes and deep component diagnostics.

## Verification Checklist
1. **Liveness & Readiness**: Query `/healthz`, `/readyz`, or `/api/v1/health` to ensure basic HTTP service availability.
2. **Deep Dependency Check**:
   - Database read/write probe
   - Redis cache ping and latency
   - Translation engine status (local vs cloud providers)
   - Audio worker queue responsiveness
3. **Telemetry & Log Sanity**: Verify that logs are streaming with valid request IDs and trace IDs, free of unhandled exception loops.
4. **Synthetic User Transaction**: Execute an automated minimal end-to-end request (e.g. login, translate 1 phrase) to verify full pipeline health.
