"""Regression coverage for the browser checklist runner's local setup."""
from __future__ import annotations

import importlib.util
from pathlib import Path


RUNNER_PATH = Path(__file__).with_name("runner.py")


def _runner_module():
    spec = importlib.util.spec_from_file_location("browser_e2e_runner", RUNNER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resolve_browser_executable_uses_first_existing_candidate(tmp_path: Path):
    """The checklist must start on installations without the legacy Edge path."""
    runner = _runner_module()
    available = tmp_path / "EdgeCore" / "msedge.exe"
    available.parent.mkdir()
    available.touch()

    resolved = runner.resolve_browser_executable((tmp_path / "missing.exe", available))

    assert resolved == str(available)
