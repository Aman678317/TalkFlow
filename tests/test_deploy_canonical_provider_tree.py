"""The deployment must not swap the canonical provider tree for the stale mirror.

Evidence behind this suite (2026-10-22, the day-2 ownership map, finding #1):

``vercel.json``'s API install command used to run

    pip install ../../ai && python -c "shutil.copytree('../../ai/gt_ai',
                                                     './gt_ai', dirs_exist_ok=True); ..."

The service root is ``services/api``, so ``./gt_ai`` **is** the canonical
provider tree — the copy merged the legacy lane's ``ai/gt_ai`` over it. The
copy was harmless while the two trees were identical (they were, when the
command was written), but they have drifted: 8 canonical files differ and 3
exist only in the canonical tree. So the serverless build silently replaced

* the cache-first Silero gate (the #113 class-2 fix) with the legacy copy,
* the ``neural_online`` echo guard with a version that accepts the source
  text as a translation,
* the AirLLM adapter registration (it vanishes from the MT chain),
* the richer Azure adapters, and
* the ``gt_ai.stt`` / ``gt_ai.translation`` package exports.

``pip install ../../ai`` had the same effect from the other side: it
installs the **mirror** as the top-level ``gt_ai`` package (the mirror's
``ai/pyproject.toml`` declares ``include = ["gt_ai*"]``), so the stale
package sits in site-packages next to the canonical one. Nothing in
``services/api`` imports the legacy ``ai`` package, so nothing needs it.

Pinned here: the install command must not write into the canonical
provider tree, must not install the mirror as ``gt_ai``, and must keep
copying the multi-agent portfolio (the Agent Studio feature depends on it).
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VERCEL = REPO / "vercel.json"


def _api_install_command() -> str:
    config = json.loads(VERCEL.read_text(encoding="utf-8"))
    return config["services"]["api"]["installCommand"]


def test_the_api_service_root_is_the_canonical_tree():
    config = json.loads(VERCEL.read_text(encoding="utf-8"))
    assert config["services"]["api"]["root"] == "services/api", (
        "the API service root must stay services/api — the canonical provider "
        "tree lives inside it")
    assert config["services"]["api"]["entrypoint"] == "app.main:app"


def test_the_install_command_does_not_overwrite_the_canonical_provider_tree():
    cmd = _api_install_command()
    assert "'./gt_ai'" not in cmd and '"./gt_ai"' not in cmd, (
        "the install command must not copy the legacy lane over the canonical "
        "provider tree — the two have drifted")
    assert "copytree('../../ai/gt_ai'" not in cmd, (
        "the legacy lane must not be copied into the canonical tree")


def test_the_install_command_does_not_install_the_mirror_as_gt_ai():
    cmd = _api_install_command()
    assert "pip install ../../ai" not in cmd, (
        "installing the legacy lane puts the STALE mirror on sys.path as the "
        "top-level gt_ai package; nothing in services/api imports it")


def test_the_multi_agent_portfolio_is_still_copied():
    """The Agent Studio feature resolves the portfolio next to the service."""
    cmd = _api_install_command()
    assert "copytree('../../multi-agent-portfolio', './multi_agent_portfolio'" in cmd, (
        "the Agent Studio's bridge.py lives in the multi-agent portfolio and "
        "must still be copied next to the service")


def test_the_canonical_tree_is_the_one_the_service_imports():
    """The service imports the canonical `gt_ai`, and it is inside the root."""
    canonical = REPO / "services" / "api" / "gt_ai"
    assert (canonical / "model_router" / "router.py").exists()
    assert (canonical / "translation" / "airllm.py").exists(), (
        "the canonical tree has modules the mirror never had — copying the "
        "mirror over it would delete them from the deployed package")
