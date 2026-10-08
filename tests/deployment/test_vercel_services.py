import json
from pathlib import Path


def _config():
    return json.loads(Path("vercel.json").read_text())


def test_vercel_services_have_expected_roots_and_frameworks():
    config = _config()
    services = config["services"]
    service_names = [service["name"] for service in services]

    assert service_names == ["web", "api", "connect"]

    by_name = {service["name"]: service for service in services}

    assert by_name["web"]["root"] == "apps/web"
    assert by_name["web"]["framework"] == "vite"

    assert by_name["api"]["root"] == "services/api"
    assert by_name["api"]["framework"] == "fastapi"
    assert by_name["api"]["entrypoint"] == "app.main:app"
    assert "../../ai" in by_name["api"]["installCommand"]

    assert by_name["connect"]["root"] == "apps/amazon-connect-v2v/webapp"
    assert by_name["connect"]["framework"] == "vite"


def test_vercel_rewrites_route_specific_paths_before_web_catchall():
    config = _config()
    routes = config["routes"]

    route_map = {route["src"]: route for route in routes}

    for src in [
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
        assert src in route_map
        assert route_map[src]["dest"].startswith("https://api")

    assert route_map["/connect"]["dest"].startswith("https://connect")
    assert route_map["/connect/:path*"]["dest"].startswith("https://connect")
    assert route_map["/connect/:path*"]["dest"].endswith("/:path*")
    assert route_map["/(.*)"]["dest"].startswith("https://web")


def test_services_do_not_define_unneeded_bindings():
    config = _config()
    services = config["services"]

    for service in services:
        assert "serviceBinding" not in service
        assert "bindings" not in service
