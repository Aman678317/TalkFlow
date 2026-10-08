import json
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VERCEL_CONFIG = ROOT / "vercel.json"
API_PROJECT = ROOT / "services/api/pyproject.toml"
CONNECT_VITE_CONFIG = ROOT / "apps/amazon-connect-v2v/webapp/vite.config.js"
WEB_APP = ROOT / "apps/web/src/App.tsx"


def load_vercel_config() -> dict:
    return json.loads(VERCEL_CONFIG.read_text(encoding="utf-8"))


def test_vercel_services_have_expected_roots_and_frameworks():
    services = load_vercel_config()["services"]

    assert set(services) == {"web", "api", "connect"}
    assert services["web"]["root"] == "apps/web"
    assert services["web"]["framework"] == "vite"
    assert services["api"]["root"] == "services/api"
    assert services["api"]["framework"] == "fastapi"
    assert services["api"]["entrypoint"] == "app.main:app"
    assert services["connect"]["root"] == "apps/amazon-connect-v2v/webapp"
    assert services["connect"]["framework"] == "vite"


def test_vercel_rewrites_route_specific_paths_before_web_catchall():
    rewrites = load_vercel_config()["rewrites"]

    assert [(rule["source"], rule["destination"]["service"]) for rule in rewrites] == [
        ("/api/(.*)", "api"),
        ("/api", "api"),
        ("/api-docs", "api"),
        ("/v2/(.*)", "api"),
        ("/v3/(.*)", "api"),
        ("/ws/(.*)", "api"),
        ("/health", "api"),
        ("/healthz", "api"),
        ("/ready", "api"),
        ("/readyz", "api"),
        ("/metrics", "api"),
        ("/connect", "connect"),
        ("/connect/:path*", "connect"),
        ("/(.*)", "web"),
    ]
    assert rewrites[-3]["destination"]["path"] == "/"
    assert rewrites[-2]["destination"]["path"] == "/:path*"


def test_services_do_not_define_unneeded_bindings():
    services = load_vercel_config()["services"]

    assert all(not service.get("bindings") for service in services.values())


def test_connect_vite_build_uses_its_public_path_prefix():
    vite_config = CONNECT_VITE_CONFIG.read_text(encoding="utf-8")

    assert 'base: "/connect/"' in vite_config


def test_web_copilotkit_defaults_to_the_public_api_route():
    app_source = WEB_APP.read_text(encoding="utf-8")

    assert (
        "const runtimeUrl = import.meta.env.VITE_COPILOTKIT_RUNTIME_URL "
        "|| '/api/copilotkit';"
    ) in app_source


def test_api_declares_dependencies_for_the_copilotkit_endpoint():
    project = tomllib.loads(API_PROJECT.read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]
    dependency_names = {dependency.split(">=")[0] for dependency in dependencies}

    assert {"langchain-core", "langchain-openai", "langgraph"} <= dependency_names


def test_api_resolves_gt_ai_from_the_repository_source():
    project = tomllib.loads(API_PROJECT.read_text(encoding="utf-8"))
    source = project["tool"]["uv"]["sources"]["gt-ai"]

    assert source["path"] == "../../ai"
    assert (API_PROJECT.parent / source["path"]).resolve() == (ROOT / "ai").resolve()
