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


def test_the_serverless_manifest_stays_under_the_function_size_cap():
    """The Vercel Python function bundle is hard-capped at 225 MB.

    Deployment dpl_BqUUhr2XCpbhCFTptQ9afgf8B5R5 failed with
    LAMBDA_SIZE_EXCEEDED at 236.27 MB while installing the branch's
    runtime-crypto fix (pyjwt[crypto] + cryptography) on top of a manifest
    that also carried the azure Speech SDK and the uvicorn [standard]
    extras:

    * azure-cognitiveservices-speech ≈ 7.9 MB unpacked + azure-core /
      requests / urllib3 / charset_normalizer ≈ 1.6 MB — and the SDK is
      only ever imported inside gt_ai.stt.azure_speech methods, which fail
      close with a ``pip install azure-cognitiveservices-speech`` hint
      when it is absent. Vercel has no credentials, so the provider is
      never selected there anyway.
    * uvloop ≈ 17 MB and httptools ≈ 1.9 MB unpacked are local-dev
      conveniences ([standard] extra); the serverless worker does not use
      them. watchfiles stays pinned so ``uvicorn --reload`` keeps its
      fast file watcher in dev.

    The prod install path for the SDK remains the `azure` pyproject extra.
    """
    reqs = (REPO / "services" / "api" / "requirements.txt").read_text(encoding="utf-8")
    # Only spec lines pin; prose comments may still name the package in the
    # install-hint story.
    deps = [line.strip() for line in reqs.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]
    assert not any(dep.startswith("azure-cognitiveservices-speech") for dep in deps), (
        "the serverless Python manifest must not pin azure-cognitiveservices-"
        "speech: its native wheel tipped the lambda bundle past the 225 MB "
        "cap; the provider fails close with an install hint when the SDK is "
        "absent, and the opt-in pyproject extra remains the install path")
    assert not any(dep.startswith("uvicorn[") for dep in deps), (
        "uvloop/httptools are local-dev extras the serverless worker never "
        "imports; pinning them through [standard] put ~19 MB into an already "
        "over-cap bundle")
    assert any(dep.startswith("uvicorn") for dep in deps), (
        "the uvicorn pin itself must survive the trim — only the extras go")
    pyproject = (REPO / "services" / "api" / "pyproject.toml").read_text(encoding="utf-8")
    assert '"azure-cognitiveservices-speech' in pyproject, (
        "trimming the runtime pin must not remove the opt-in path: the azure "
        "extra stays the explicit install for credential-bearing hosts")
    assert any(dep.startswith("watchfiles") for dep in deps), (
        "uvicorn --reload needs watchfiles for its fast file watcher; the "
        "manifest keeps it explicitly while the [standard] extras are gone")
