#!/usr/bin/env bash
# Dev runner: the backend the frontend can actually reach.
#
# `apps/web/vite.config.ts` proxies /api, /ws, /health, /ready and /metrics to
# 127.0.0.1:8088, and `services/api` is the tree Render deploys — so this starts
# THAT tree on THAT port. It used to start `apps/api` (module `globaltalk`, the
# legacy tree) on :8000, which left the UI with no backend: every proxied call
# failed even though `make dev` looked healthy. `make api-legacy` still runs the
# old tree on :8000 if you need it.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="services/api:apps/api:."
export MALLOC_ARENA_MAX=2
export APP_ENV=development
trap 'kill 0' EXIT
python3 run_api.py &
(cd apps/web && npx vite --host 127.0.0.1 --port 5173) &
wait
