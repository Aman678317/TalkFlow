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
    """The canonical provider tree carries the fixes the fork never got.

    The fork that used to live at ``ai/gt_ai`` had an older SileroVAD (the
    threshold-flip version, where a turn could end mid-sentence) and no
    AirLLM adapter at all. Those fixes live in the canonical tree, which is
    now the only one.
    """
    canonical = _silero_class((CANONICAL / "vad.py").read_text(encoding="utf-8"))
    # the canonical SileroVAD carries the turn-debounce rules (#113)
    assert "max_speech_ms" in canonical
    assert "min_silence_ms" in canonical
    # the AirLLM adapter is part of the canonical tree
    assert (CANONICAL / "translation" / "airllm.py").exists()
    registry = (CANONICAL / "registry.py").read_text(encoding="utf-8")
    assert "gt_ai.translation.airllm" in registry


def test_the_repo_root_cannot_shadow_the_canonical_package():
    """The root SDK used to be named ``gt_ai`` and could win the import.

    If the root ever carries a ``gt_ai`` package again, a plain ``python``
    from the repo root would import the SDK instead of the provider package —
    and the SDK has no ``NoPrivateProviderAvailable`` and a different
    ``Intent`` base, so the whole AI facade would fail to import with an
    ImportError that points nowhere near the cause.
    """
    assert not (REPO / "gt_ai").exists(), (
        "the repo root must not carry a 'gt_ai' package: it shadows the "
        "canonical provider package (the public SDK is 'gt_ai_sdk')")
    assert (REPO / "gt_ai_sdk" / "__init__.py").exists(), (
        "the public SDK must keep its (renamed) package")
    # and the canonical provider package is where it says it is
    assert (CANONICAL / "__init__.py").exists()


def test_the_provider_fork_is_retired():
    """There is ONE provider layer: services/api/gt_ai.

    The fork that used to live at ``ai/gt_ai`` was a drifted copy of it
    (8 files differed, 3 existed only in the canonical tree) and it was the
    tree the legacy lane and the GPU worker resolved. A second copy of a
    provider layer is how the fixes stop reaching one of the lanes.
    """
    assert not (REPO / "ai" / "gt_ai").exists(), (
        "the provider fork must not come back: services/api/gt_ai is the one "
        "provider layer")
    # the legacy lane keeps its OWN adapters (a different interface, not a
    # fork of the provider package) — those stay.
    assert (REPO / "ai" / "providers" / "vad.py").exists()
