#!/usr/bin/env bash
# Dev runner: API on :8000, Web on :5173 (Vite proxies /api and /ws to the API).
#
# The API is the CANONICAL backend (services/api) — the same code the image
# runs. It used to start the LEGACY tree (apps/api, `globaltalk.main:app`),
# which meant a developer following the documented command debugged a tree the
# product does not use, and whose providers come from the legacy lane
# (issue #109 class 3, day-2 finding O-10).
#
# The legacy lane is still one command away:  DEV_LEGACY=1 bash scripts/run_dev.sh
cd "$(dirname "$0")/.."
export MALLOC_ARENA_MAX=2
export API_PORT="${API_PORT:-8000}"

if [ "${DEV_LEGACY:-0}" = "1" ]; then
  echo "Starting the LEGACY backend (apps/api) on :8000"
  export PYTHONPATH="apps/api:."
  trap 'kill 0' EXIT
  python3 -m uvicorn globaltalk.main:app --host 127.0.0.1 --port 8000 --reload &
else
  echo "Starting the CANONICAL backend (services/api) on :8000"
  export PYTHONPATH="services/api:apps/api:ai:."
  trap 'kill 0' EXIT
  python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload &
fi

(cd apps/web && npx vite --port 5173) &
wait
