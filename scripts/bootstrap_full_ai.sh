#!/usr/bin/env bash
# GlobalTalk AI — full bootstrap (section 83). Detects toolchain, installs dependencies,
# initializes environment + database, and verifies the AI stack.
# Usage: PROFILE=CPU_DEV|GPU_DEV|GPU_PRODUCTION|HYBRID bash scripts/bootstrap_full_ai.sh
set -uo pipefail
cd "$(dirname "$0")/.."
PROFILE="${PROFILE:-CPU_DEV}"

ok()   { echo "[OK]       $1"; }
warn() { echo "[WARN]     $1"; }
fail() { echo "[FAILED]   $1"; FAILURES=$((FAILURES+1)); }
opt()  { echo "[OPTIONAL] $1"; }
FAILURES=0

echo "== GlobalTalk AI bootstrap (profile: $PROFILE) =="

# ---------------------------------------------------------- toolchain detection
command -v git >/dev/null && ok "git $(git --version | cut -d' ' -f3)" || fail "git missing"
command -v python3 >/dev/null && ok "python $(python3 -V | cut -d' ' -f2)" || fail "python3 missing"
command -v node >/dev/null && ok "node $(node -v)" || warn "node missing (web UI needs Node 18+)"
command -v npm >/dev/null && ok "npm $(npm -v)" || warn "npm missing"
command -v docker >/dev/null && ok "docker $(docker --version | cut -d' ' -f3 | tr -d ',')" || opt "docker not installed — dev runs without it"
command -v docker-compose >/dev/null 2>&1 || docker compose version >/dev/null 2>&1 \
  && ok "docker compose available" || opt "docker compose missing"
command -v psql >/dev/null && ok "psql $(psql --version | cut -d' ' -f3)" || opt "postgresql client not found (SQLite used in dev)"
command -v redis-server >/dev/null && ok "redis-server present" || opt "redis not installed (in-process cache fallback active)"
command -v ffmpeg >/dev/null && ok "ffmpeg $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f3)" || warn "ffmpeg missing — audio conversions limited"
if command -v nvidia-smi >/dev/null && nvidia-smi -L >/dev/null 2>&1; then
  ok "NVIDIA GPU detected: $(nvidia-smi -L | head -1)"
  command -v nvcc >/dev/null && ok "CUDA toolkit $(nvcc --version | grep release | sed 's/.*release //;s/,.*//')" || opt "CUDA toolkit not on PATH"
else
  opt "no NVIDIA GPU — CPU inference profile"
fi

# ---------------------------------------------------------- environment
if [ ! -f .env ]; then cp .env.example .env && ok ".env created from .env.example"; else ok ".env exists"; fi
mkdir -p data data/storage "${MODEL_CACHE_PATH:-/tmp/globaltalk-models}"

# ---------------------------------------------------------- python deps
echo "-- installing python dependencies (CPU wheels) --"
# services/api is the tree `make dev`/`make api` starts and the tree Render deploys
# (README points here too); apps/api is the legacy tree the golden test drives. The
# two have separate requirements files, and installing only the legacy one leaves the
# shipped backend without its dependencies.
pip install -q --no-input -r services/api/requirements.txt \
  && ok "services/api requirements installed" || fail "pip install (services/api) failed"
pip install -q --no-input -r apps/api/requirements.txt \
  && ok "apps/api requirements installed" || fail "pip install (apps/api) failed"
# livekit SDKs: optional, needed only when LIVEKIT_* is configured
if [ "${WITH_LIVEKIT:-false}" = "true" ]; then
  pip install -q --no-input "livekit-api==0.8.2" && ok "livekit-api installed" || warn "livekit-api install failed"
else
  opt "livekit-api skipped (set WITH_LIVEKIT=true; WebSocket transport used otherwise)"
fi
# docling: optional parser upgrade
if [ "${WITH_DOCLING:-false}" = "true" ]; then
  pip install -q --no-input "docling==2.67.0" && ok "docling installed" || warn "docling install failed"
else
  opt "docling skipped (built-in parsers active: pypdf/python-docx/python-pptx/openpyxl)"
fi

# ---------------------------------------------------------- node deps
if command -v npm >/dev/null; then
  (cd apps/web && npm install --no-audit --no-fund >/dev/null 2>&1 && ok "web dependencies installed") || fail "npm install failed"
fi

# ---------------------------------------------------------- database
echo "-- initializing database --"
# Seed the tree you are about to run. This used to import `globaltalk.core.db` /
# `globaltalk.seed`, which builds the LEGACY backend's database, so a fresh
# "bootstrap complete" left services/api with no tables and no seeded
# admin@globaltalk.dev account — the one docs/LOCAL_DEVELOPMENT.md tells you to sign
# in with. `alembic upgrade head` matches services/api/start.sh, so dev and prod get
# the same schema; set SEED_LEGACY=true to seed apps/api as well.
export PYTHONPATH="services/api:apps/api:."
(cd services/api && python3 -m alembic upgrade head) \
  && ok "services/api schema migrated" || fail "services/api migration failed"
(cd services/api && python3 -c "import asyncio; from app.seed import run_seed; asyncio.run(run_seed())") \
  && ok "services/api seeded (languages, flags, styles, model registry, demo org)" \
  || fail "services/api seed failed"
if [ "${SEED_LEGACY:-false}" = "true" ]; then
  (cd apps/api && PYTHONPATH="apps/api:." python3 - <<'EOF' && ok "legacy apps/api database initialized + seeded" || fail "legacy seed failed"
from globaltalk.core.db import init_db
init_db()
from globaltalk.seed import seed_all
seed_all()
EOF
  )
else
  opt "legacy apps/api seed skipped (set SEED_LEGACY=true; only tests/realtime/test_golden_call.py needs it)"
fi

# ---------------------------------------------------------- model weights
if [ "${SKIP_MODELS:-false}" != "true" ]; then
  echo "-- downloading model weights (this can take a while) --"
  MODEL_PROFILE="${MODEL_PROFILE:-CPU}" bash scripts/download_models.sh || warn "model download incomplete — see output above"
else
  opt "model download skipped (SKIP_MODELS=true)"
fi

# ---------------------------------------------------------- verification
echo "-- verifying AI stack --"
python3 scripts/verify_ai_stack.py --quick || warn "AI stack verification reported issues"

echo
if [ "$FAILURES" -eq 0 ]; then
  ok "bootstrap complete — start with: make dev"
else
  fail "$FAILURES step(s) failed — review output above"
  exit 1
fi
