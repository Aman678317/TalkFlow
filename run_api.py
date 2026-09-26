import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API_DIR = ROOT / "services" / "api"
AI_DIR = ROOT / "ai"

# Ensure data directory exists so SQLite doesn't fail
(ROOT / "data").mkdir(parents=True, exist_ok=True)
(API_DIR / "data").mkdir(parents=True, exist_ok=True)

# Add directories to Python module search path
sys.path.insert(0, str(API_DIR))
sys.path.insert(0, str(AI_DIR))

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
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
