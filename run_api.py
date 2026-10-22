import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API_DIR = ROOT / "services" / "api"
AI_DIR = ROOT / "ai"

# Ensure data directory exists so SQLite doesn't fail
(ROOT / "data").mkdir(parents=True, exist_ok=True)
(API_DIR / "data").mkdir(parents=True, exist_ok=True)

# Add directories to Python module search path.
#
# ORDER MATTERS: the LAST insert lands at sys.path[0], and the CANONICAL
# provider tree must win. `ai/gt_ai` is the legacy lane's copy of the same
# package and it has drifted (8 files differ, 3 exist only in the canonical
# tree — see docs/ARCHITECTURE_OWNERSHIP.md §8). With `ai` inserted last,
# the dev server imported the stale mirror: no AirLLM adapter, no cache-first
# Silero gate, no echo guard.
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
