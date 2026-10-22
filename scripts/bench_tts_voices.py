#!/usr/bin/env python
"""Run the Phase 3 target-language voice benchmark from anywhere in the repo.

``gt_ai`` has to be resolved to the package under ``ai/`` — so the path has to
be set explicitly, because the voice directory has to be an absolute path and
the API runs with ``services/api`` as its cwd. (The repo root used to carry
an unrelated ``gt_ai`` SDK that could shadow the provider package; that SDK
is now ``gt_ai_sdk`` and can no longer shadow anything.)

    python scripts/bench_tts_voices.py --lang en,hi,ur
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ai"))

from gt_ai.evaluation.tts import main  # noqa: E402


def _default_model_dir() -> str:
    """Where the deployed API would look for Piper voices, as an absolute path.

    ``PiperProvider``'s own default is relative, and the API runs with
    ``services/api`` as its working directory — so a benchmark run from the repo
    root would report every installed voice as missing.
    """
    cache = os.environ.get("MODEL_CACHE_PATH", "")
    base = Path(cache) if cache else ROOT / "services" / "api" / "model_cache"
    return str(base / "piper")


if __name__ == "__main__":
    if "--model-dir" not in sys.argv:
        sys.argv += ["--model-dir", _default_model_dir()]
    main()
