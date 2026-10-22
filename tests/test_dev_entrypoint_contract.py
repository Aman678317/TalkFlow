"""`make dev` must start the backend the product actually runs.

Evidence behind this suite (2026-10-22, the day-2 ownership map, finding
O-10):

``make dev`` ran ``scripts/run_dev.sh``, which set
``PYTHONPATH="apps/api:."`` and started ``uvicorn globaltalk.main:app`` — the
LEGACY compatibility tree, with its own models, its own Alembic lineage and
its own provider lane. So a developer following the documented command
debugged a tree the product does not use, and every fix made in
``services/api/gt_ai`` was invisible locally.

The dev runner now starts the CANONICAL backend (``services/api``), the same
code the image runs, and the legacy lane has its own target
(``make dev-legacy`` / ``DEV_LEGACY=1``).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "scripts" / "run_dev.sh"
MAKEFILE = REPO / "Makefile"


def _runner() -> str:
    return RUNNER.read_text(encoding="utf-8")


def test_the_dev_runner_starts_the_canonical_backend():
    src = _runner()
    assert "uvicorn app.main:app" in src, (
        "the dev runner must start the canonical app (services/api) by default")
    assert 'PYTHONPATH="services/api:apps/api:ai:."' in src, (
        "the canonical tree must be on the path")
    # the legacy app must only start when it is asked for
    legacy_branch = src[src.index("if [ \"${DEV_LEGACY"):src.index("else")]
    canonical_branch = src[src.index("else"):]
    assert "globaltalk.main:app" in legacy_branch, (
        "the legacy app belongs in the opt-in branch")
    assert "app.main:app" in canonical_branch, (
        "the canonical app belongs in the default branch")


def test_the_legacy_lane_is_still_one_command_away():
    src = _runner()
    assert "DEV_LEGACY" in src, (
        "the legacy compatibility lane must stay reachable for the people who "
        "maintain it")
    assert "uvicorn globaltalk.main:app" in src


def test_the_makefile_exposes_both_targets():
    src = MAKEFILE.read_text(encoding="utf-8")
    assert re.search(r"^dev:\s*\n\s*@bash scripts/run_dev\.sh", src, re.M), (
        "`make dev` must run the dev runner")
    assert re.search(r"^dev-legacy:\s*\n\s*@DEV_LEGACY=1 bash scripts/run_dev\.sh", src, re.M), (
        "the legacy lane must have its own target")
