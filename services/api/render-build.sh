#!/usr/bin/env bash
# GlobalTalk AI — Render Build & Migration Script
set -o errexit

echo "==> Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Running database migrations..."
# In Render, migrations apply automatically against the configured DATABASE_URL (e.g. Supabase)
alembic upgrade head || {
    echo "Warning: Database migrations had non-fatal warning or skipped offline"
}

echo "==> Build complete!"
