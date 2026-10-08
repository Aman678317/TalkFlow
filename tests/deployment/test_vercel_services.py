import json
from pathlib import Path


def _config():
    return json.loads(Path("vercel.json").read_text())


def test_vercel_services_use_named_service_configuration():
    services = _config()["services"]

    assert set(services) == {"web", "api", "connect"}
    assert services["web"]["root"] == "apps/web"
    assert services["web"]["framework"] == "vite"
    assert services["api"]["root"] == "services/api"
    assert services["api"]["framework"] == "fastapi"
    assert services["api"]["entrypoint"] == "app.main:app"
    assert "../../ai" in services["api"]["installCommand"]
    assert services["connect"]["root"] == "apps/amazon-connect-v2v/webapp"
    assert services["connect"]["framework"] == "vite"


def test_vercel_rewrites_route_api_and_connect_before_the_web_catchall():
    rewrites = _config()["rewrites"]
    rewrite_map = {rewrite["source"]: rewrite["destination"] for rewrite in rewrites}

    for source in [
        "/api-docs",
        "/api",
        "/api/:path*",
        "/v2/:path*",
        "/v3/:path*",
        "/ws/:path*",
        "/health",
        "/healthz",
        "/ready",
        "/readyz",
        "/metrics",
    ]:
        assert rewrite_map[source] == {"service": "api"}

    assert rewrite_map["/connect"] == {"service": "connect", "path": "/"}
    assert rewrite_map["/connect/:path*"] == {
        "service": "connect",
        "path": "/:path*",
    }
    assert rewrite_map["/(.*)"] == {"service": "web"}
    assert rewrites[-1]["source"] == "/(.*)"


def test_services_do_not_define_unneeded_bindings():
    services = _config()["services"]

    for service in services.values():
        assert "bindings" not in service
