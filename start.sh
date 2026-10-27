#!/usr/bin/env bash
set -e

if [ -d "services/api" ]; then
  cd services/api
fi

alembic upgrade head || true
PORT="${PORT:-8000}"
echo "Starting TalkFlow on port ${PORT}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
