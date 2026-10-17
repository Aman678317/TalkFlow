import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API_DIR = ROOT / "services" / "api"
AI_DIR = ROOT / "ai"

# Ensure data directory exists so SQLite doesn't fail
(ROOT / "data").mkdir(parents=True, exist_ok=True)
(API_DIR / "data").mkdir(parents=True, exist_ok=True)

# Module search path. ORDER MATTERS: the repo carries two `gt_ai` packages —
# `ai/gt_ai`, used by the legacy `apps/api` backend, and `services/api/gt_ai`, the
# one this backend's code is written against. Whichever comes first wins, and it has
# to be `services/api`: app.ai builds ModelRouter(..., breakers=...), which the older
# `ai/gt_ai` signature does not accept, so startup dies with a TypeError before
# anything listens. This is also the order pytest uses (pyproject.toml pythonpath)
# and the order Render gets, where rootDir: services/api makes it the cwd.
sys.path.insert(0, str(AI_DIR))
sys.path.insert(0, str(API_DIR))

# Change current working directory to services/api
os.chdir(str(API_DIR))
os.environ["APP_ENV"] = "development"

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8088))
    print(f"============================================================")
    print(f"Starting GlobalTalk AI backend on http://127.0.0.1:{port}")
    print(f"Docs available at: http://127.0.0.1:{port}/api/docs")
    print(f"============================================================")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True, reload_dirs=[str(API_DIR), str(AI_DIR)])
