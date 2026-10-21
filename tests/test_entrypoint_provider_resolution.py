"""Every entry point must import the CANONICAL provider tree.

Evidence behind this suite (2026-10-22, the day-2 ownership map, findings
#2 and O-9):

``run_api.py`` (the documented dev server) and
``workers/inference-worker/main.py`` (the GPU worker) both put the legacy
lane's ``ai/`` directory on ``sys.path`` LAST — and the last insert lands at
``sys.path[0]``, so the stale ``ai/gt_ai`` mirror won. The mirror has
drifted from the canonical ``services/api/gt_ai``: 8 files differ and 3 exist
only in the canonical tree, so the dev server and the GPU worker ran a
provider layer without the AirLLM adapter (its registry raises ``KeyError``),
without the cache-first Silero gate, and without the DeepL echo guard — while
the inference worker also imported the canonical app, so the two trees met
inside one process.

Pinned here: each entry point resolves the canonical package, measured by
actually importing it in a subprocess — not by reading the source.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CANONICAL = REPO / "services" / "api" / "gt_ai"
MIRROR = REPO / "ai" / "gt_ai"


def _resolved_gt_ai(code: str) -> str:
    out = subprocess.run([sys.executable, "-c", code], cwd=str(REPO),
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise AssertionError(f"the probe failed: {out.stderr.strip()[-400:]}")
    return out.stdout.strip().splitlines()[-1]


def test_the_dev_server_resolves_the_canonical_provider_tree():
    resolved = _resolved_gt_ai(
        "import importlib, sys\n"
        "importlib.import_module('run_api')\n"
        "import gt_ai\n"
        "print(gt_ai.__file__)\n")
    assert Path(resolved).resolve().is_relative_to(CANONICAL.resolve()), (
        f"the dev server imported {resolved} — the legacy mirror must not win")


def test_the_gpu_worker_resolves_the_canonical_provider_tree():
    resolved = _resolved_gt_ai(
        "import importlib.util, sys\n"
        "spec = importlib.util.spec_from_file_location('inf_worker',"
        " 'workers/inference-worker/main.py')\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(mod)\n"
        "import gt_ai\n"
        "print(gt_ai.__file__)\n")
    assert Path(resolved).resolve().is_relative_to(CANONICAL.resolve()), (
        f"the GPU worker imported {resolved} — the legacy mirror must not win")


def _silero_class(text: str) -> str:
    """The SileroVAD class body (EnergyVAD has the same parameter names)."""
    return text[text.index("class SileroVAD:"):]


def test_the_canonical_tree_is_the_one_that_carries_the_fixes():
    """The mirror lacks these; the canonical tree has them.

    If this test starts failing, the mirror was re-synced — and the drift
    table in docs/ARCHITECTURE_OWNERSHIP.md §8.1 needs a refresh.
    """
    canonical = _silero_class((CANONICAL / "vad.py").read_text(encoding="utf-8"))
    mirror = _silero_class((MIRROR / "vad.py").read_text(encoding="utf-8"))
    # the canonical SileroVAD carries the turn-debounce rules (#113); the
    # mirror's is the older threshold-flip version (a turn can end mid-word)
    assert "max_speech_ms" in canonical
    assert "max_speech_ms" not in mirror, (
        "the mirror's SileroVAD is expected to be the pre-#113 copy — if this "
        "changes, the mirror was re-synced and the drift table needs a refresh")
    # the AirLLM adapter exists only in the canonical tree, and the mirror's
    # registry never imports it — so the mirror cannot build that provider
    assert (CANONICAL / "translation" / "airllm.py").exists()
    assert not (MIRROR / "translation" / "airllm.py").exists()
    mirror_registry = (MIRROR / "registry.py").read_text(encoding="utf-8")
    assert "gt_ai.translation.airllm" not in mirror_registry
