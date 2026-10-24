"""The metrics endpoint must never be served unauthenticated in production.

Evidence behind this suite (2026-10-22, the day-2 ownership map, finding
C-4):

``GET /metrics`` exposed the Prometheus series — which include
**tenant-labelled** counters and latency histograms — and the token was
checked only when the deployment was production AND a token was
configured. So:

* a production deployment with no ``METRICS_TOKEN`` served the metrics to
  anyone (the token check was skipped entirely);
* a staging deployment with a token configured served them to anyone too
  (the check was production-only).

Pinned here: production refuses to boot with the endpoint enabled and no
token, a configured token is enforced in EVERY environment, and a
development deployment without a token keeps the open endpoint it has
always had.
"""
from __future__ import annotations

import pytest

from app.config import Settings


def _prod_base() -> dict:
    """The same production baseline the other production-gate suites use."""
    return {
        "app_env": "production",
        "secret_key": "a" * 32,
        "jwt_secret": "b" * 32,
        "redis_url": "redis://localhost:6379/0",
        "database_url": "postgresql+asyncpg://user:pass@localhost:5432/dbname",
        "cors_origins": ["https://app.globaltalk.ai"],
    }


def test_production_refuses_to_boot_with_metrics_enabled_and_no_token():
    with pytest.raises(ValueError, match="metrics_token"):
        Settings(**_prod_base(), metrics_enabled=True, metrics_token="")
    with pytest.raises(ValueError, match="metrics_token"):
        Settings(**_prod_base(), metrics_enabled=True, metrics_token="")


def test_production_boots_with_metrics_disabled():
    s = Settings(**_prod_base(), metrics_enabled=False, metrics_token="")
    assert s.metrics_enabled is False


def test_production_boots_with_a_metrics_token():
    s = Settings(**_prod_base(), metrics_enabled=True, metrics_token="m" * 32)
    assert s.metrics_token


def test_a_configured_token_is_enforced_outside_production():
    """The token check must not be production-only."""
    import inspect

    from app.routers import health
    src = inspect.getsource(health.metrics)
    assert "if settings.metrics_token:" in src, (
        "a configured metrics token must be enforced in every environment, not "
        "only in production (issue #109 class 3, day-2 finding C-4)")
    assert "settings.is_production and settings.metrics_token" not in src, (
        "the token check must not be gated on production any more")


def test_the_metrics_endpoint_demands_the_configured_token(services_app_client, monkeypatch):
    from app.routers import health
    # The endpoint reads the settings bound in its own module — patching the
    # test module's instance would miss it (the app.config reload forks the
    # bindings, the landmine the day-2 map records as T-1).
    monkeypatch.setattr(health.settings, "metrics_enabled", True)
    monkeypatch.setattr(health.settings, "metrics_token", "s" * 32)
    res = services_app_client.get("/metrics")
    assert res.status_code == 401, (
        f"the metrics endpoint served an unauthenticated caller: {res.status_code}")
    ok = services_app_client.get("/metrics", headers={"X-Metrics-Token": "s" * 32})
    assert ok.status_code == 200, ok.text
