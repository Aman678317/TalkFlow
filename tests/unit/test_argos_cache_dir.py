"""The Argos package cache has to be pointed at explicitly — and with the name Argos reads.

Regression: the adapter set `ARGOS_PACKAGE_FOLDER`, which no version of argostranslate
reads, so packages silently landed in the user's home data dir while the golden-call
guard looked for them in MODEL_CACHE_PATH/argos and skipped the acceptance test.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
from pathlib import Path

from ai.providers.translation import argos


def _fake_argos(monkeypatch, tmp_path: Path):
    settings = types.ModuleType("argostranslate.settings")
    settings.package_data_dir = tmp_path / "home-packages"
    settings.package_dirs = [settings.package_data_dir]
    package = types.ModuleType("argostranslate")
    package.settings = settings
    monkeypatch.setitem(sys.modules, "argostranslate", package)
    monkeypatch.setitem(sys.modules, "argostranslate.settings", settings)
    monkeypatch.delenv("ARGOS_PACKAGES_DIR", raising=False)
    return settings


def test_cache_dir_uses_the_env_name_argos_actually_reads(tmp_path, monkeypatch):
    settings = _fake_argos(monkeypatch, tmp_path)
    root = tmp_path / "models" / "argos"

    argos._use_cache_dir(str(root))

    assert os.environ["ARGOS_PACKAGES_DIR"] == str(root)
    assert settings.package_data_dir == root
    assert settings.package_dirs[0] == root
    assert root.is_dir()


def test_existing_package_dirs_are_kept_searchable(tmp_path, monkeypatch):
    settings = _fake_argos(monkeypatch, tmp_path)
    home = settings.package_data_dir

    argos._use_cache_dir(str(tmp_path / "models" / "argos"))
    argos._use_cache_dir(str(tmp_path / "models" / "argos"))

    assert settings.package_dirs.count(home) == 1, "already-installed packages stay visible"
    assert len(settings.package_dirs) == 2, "pointing twice must not grow the search path"


def _golden_guard():
    path = Path(__file__).resolve().parents[1] / "realtime" / "test_golden_call.py"
    spec = importlib.util.spec_from_file_location("golden_call_guard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_golden_guard_reads_a_real_argos_package_layout(tmp_path, monkeypatch):
    guard = _golden_guard()
    installed = tmp_path / "argos" / "argostranslate_hi_en-1.0"
    installed.mkdir(parents=True)
    (installed / "metadata.json").write_text(json.dumps({"from_code": "hi", "to_code": "en"}),
                                            encoding="utf-8")
    monkeypatch.setattr(guard, "ARGOS_CACHE", tmp_path / "argos")

    assert guard._argos_pair_installed("hi", "en")
    assert not guard._argos_pair_installed("en", "hi"), "only the pairs on disk count"
