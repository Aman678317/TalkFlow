---
name: ship
description: "Production deployment and release checklist. Validates build artifacts, migrations, environment secrets, health readiness probes, graceful shutdown, and rollback procedures."
---

# Ship & Production Deployment Mode

Orchestrate zero-downtime, verified production releases.

## Pre-Release Gate
1. **Build Artifacts Verified**: Web frontend bundle built with zero errors; backend dependencies resolved cleanly.
2. **Database Migrations Checked**: Forward and backward compatibility, no locking migrations on busy tables.
3. **Environment & Secrets Audit**: Confirm all required production variables exist and have valid values without hardcoded fallbacks.
4. **Health & Readiness Endpoints**: Liveness probe (`/livez`) and readiness probe (`/readyz` or `/api/docs`) responding 200 OK.
5. **Rollback Plan**: Clear command and procedure to revert code and database if smoke tests fail.
6. **Post-Deploy Smoke Test**: Automated check of critical user pathways immediately after release.
