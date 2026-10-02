#!/usr/bin/env bash
# Dev runner: API on :8000, Web on :5173 (Vite proxies /api and /ws to the API).
cd "$(dirname "$0")/.."
export PYTHONPATH="apps/api:."
export MALLOC_ARENA_MAX=2
trap 'kill 0' EXIT
python3 -m uvicorn globaltalk.main:app --host 127.0.0.1 --port 8000 --reload &
(cd apps/web && npx vite --port 5173) &
wait
