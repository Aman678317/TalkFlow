#!/usr/bin/env bash
set -e

if [ -d "services/api" ]; then
  cd services/api
fi

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-10000}"
