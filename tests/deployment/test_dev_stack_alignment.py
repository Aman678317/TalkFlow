"""The dev launcher must start the tree the browser can reach.

`docs/PHASE0_BASELINE_AUDIT.md` recorded this divergence and it stayed broken for
two weeks anyway, because nothing checked it: CI, pytest and Render each resolve
modules a different way from `run_api.py`, so localhost could be dead while every
lane was green. These assertions pin the three things that have to agree — port,
tree, and which database gets seeded.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_vite_proxy_and_dev_launcher_use_the_same_port():
    proxy = re.findall(r"target:\s*['\"](?:ws|http)s?://127\.0\.0\.1:(\d+)",
                       _read("apps/web/vite.config.ts"))
    assert proxy, "vite.config.ts must declare a proxy target"
    assert set(proxy) == {"8088"}, f"Vite proxies to {sorted(set(proxy))}"

    launcher = _read("run_api.py")
    assert re.search(r'os\.environ\.get\("PORT",\s*8088\)', launcher), \
        "run_api.py must default to the port Vite proxies to"

    env = _read(".env.example")
    assert re.search(r"^API_PORT=8088$", env, re.M)
    assert re.search(r"^API_BASE_URL=http://localhost:8088$", env, re.M), \
        "telephony self-callbacks read API_PORT, so the template must not name a dead port"


def test_dev_launcher_puts_deployed_tree_before_the_legacy_gt_ai():
    launcher = _read("run_api.py")
    inserts = re.findall(r"sys\.path\.insert\(0, str\((\w+)\)\)", launcher)
    assert inserts[-1] == "API_DIR", (
        f"sys.path inserts {inserts}: the last insert(0, ...) wins, and it has to be "
        "services/api, because app.ai builds ModelRouter(..., breakers=...) which the "
        "older ai/gt_ai signature rejects"
    )


def test_make_targets_and_dev_script_run_the_deployed_tree():
    make = _read("Makefile")
    api_block = re.search(r"^api:\n(.*\n)*?^(?=\S)", make, re.M).group(0)
    assert "services/api" in api_block and "app.main:app" in api_block
    assert "8088" in api_block
    assert re.search(r"^api-legacy:\n.*apps/api", make, re.M), \
        "the legacy tree must stay runnable for tests/realtime/test_golden_call.py"
    assert "PYTHONPATH := services/api:apps/api" in make

    run_dev = _read("scripts/run_dev.sh")
    assert "run_api.py" in run_dev, "make dev must start the same entrypoint as the launcher"
    assert "globaltalk.main" not in run_dev


def test_bootstrap_installs_and_seeds_the_deployed_tree_by_default():
    bootstrap = _read("scripts/bootstrap_full_ai.sh")
    assert "-r services/api/requirements.txt" in bootstrap, \
        "README installs services/api requirements; bootstrap must too"
    seed_section = bootstrap.split("-- initializing database --")[1]
    assert "app.seed import run_seed" in seed_section
    # Comments are allowed to name the legacy modules (that is the history); the
    # commands that run by default are not.
    code = "\n".join(line for line in seed_section.splitlines()
                     if not line.strip().startswith("#"))
    default_branch, _, _ = code.partition("SEED_LEGACY")
    assert "globaltalk.core.db" not in default_branch, \
        "the default bootstrap path must not build only the legacy database"
