"""Phase 12: Production Security Hardening Test Suite.
Verifies:
1. Comprehensive enterprise HTTP security headers (HSTS preload, CSP, nosniff, frame-ancestors/DENY, Referrer-Policy, COOP, CORP, Permissions-Policy) on all HTTP responses.
2. CORS policy hardening in production (disallow wildcard origin with credentials, validate authorized origins on preflight).
3. Automated repository secret hygiene scanning ensuring zero hardcoded live secrets or tokens exist in tracked configurations.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings, settings
from app.middleware import SECURITY_HEADERS


def test_enterprise_security_headers_enforced(services_app_client):
    """Every HTTP response must enforce enterprise security headers."""
    test_endpoints = ["/health", "/ready", "/version", "/api/v1/health"]

    for path in test_endpoints:
        res = services_app_client.get(path)
        assert res.status_code in (200, 503)

        # 1. HSTS
        hsts = res.headers.get("strict-transport-security", "")
        assert "max-age=" in hsts
        assert "includeSubDomains" in hsts
        assert "preload" in hsts

        # 2. CSP
        csp = res.headers.get("content-security-policy", "")
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp

        # 3. Framing & MIME Sniffing Protection
        assert res.headers.get("x-content-type-options") == "nosniff"
        assert res.headers.get("x-frame-options") == "DENY"

        # 4. Referrer Policy & Cross-Origin Isolation
        assert res.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
        assert res.headers.get("cross-origin-opener-policy") == "same-origin"
        assert res.headers.get("cross-origin-resource-policy") == "same-origin"

        # 5. Permissions-Policy
        perm = res.headers.get("permissions-policy", "")
        assert "camera=" in perm
        assert "microphone=" in perm


def test_cors_production_guardrail_rejects_wildcard():
    """Production settings must reject wildcard '*' in cors_origins when credentials are enabled."""
    strong_secret = "x" * 32
    strong_jwt = "y" * 32
    valid_pg = "postgresql+asyncpg://user:pass@localhost:5432/dbname"
    valid_redis = "redis://localhost:6379/0"

    with pytest.raises(ValueError, match="forbids wildcard '\\*' in 'cors_origins'"):
        Settings(
            app_env="production",
            secret_key=strong_secret,
            jwt_secret=strong_jwt,
            redis_url=valid_redis,
            database_url=valid_pg,
            cors_origins=["*"],
        )

    # Valid specific domains pass cleanly
    prod_s = Settings(
        app_env="production",
        secret_key=strong_secret,
        jwt_secret=strong_jwt,
        redis_url=valid_redis,
        database_url=valid_pg,
        cors_origins=["https://app.globaltalk.ai", "https://admin.globaltalk.ai"],
    )
    assert "https://app.globaltalk.ai" in prod_s.cors_origins


def test_production_app_cors_uses_exact_origins_only(monkeypatch):
    """Production must not reflect *.vercel.app/devtunnel/localhost via the dev regex."""
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.testclient import TestClient

    import app.main as main_module

    prod = Settings(
        app_env="production",
        secret_key="x" * 32,
        jwt_secret="y" * 32,
        redis_url="redis://localhost:6379/0",
        database_url="postgresql+asyncpg://user:pass@localhost:5432/dbname",
        cors_origins=["https://app.globaltalk.ai"],
        metrics_enabled=False,
    )
    assert prod.cors_allow_origin_regex is None

    monkeypatch.setattr(main_module, "settings", prod)
    app = main_module.create_app()
    cors = next(m for m in app.user_middleware if m.cls is CORSMiddleware)
    assert cors.kwargs["allow_origin_regex"] is None
    assert cors.kwargs["allow_origins"] == ["https://app.globaltalk.ai"]

    client = TestClient(app)
    preflight = {
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Authorization,Content-Type",
    }
    for origin in ("https://evil.vercel.app", "http://localhost:5173"):
        blocked = client.options("/api/v1/translate", headers={"Origin": origin, **preflight})
        assert blocked.headers.get("access-control-allow-origin") is None
    allowed = client.options(
        "/api/v1/translate",
        headers={"Origin": "https://app.globaltalk.ai", **preflight},
    )
    assert allowed.headers.get("access-control-allow-origin") == "https://app.globaltalk.ai"

    dev = Settings(app_env="test", cors_origins=["http://localhost:5173"])
    assert dev.cors_allow_origin_regex is not None
    local = Settings(app_env="development")
    assert local.cors_allow_origin_regex is not None


def test_production_requires_explicit_cors_origins(monkeypatch):
    """A production boot must name its browser origins; the defaults are refused."""
    base = dict(
        app_env="production",
        secret_key="x" * 32,
        jwt_secret="y" * 32,
        redis_url="redis://localhost:6379/0",
        database_url="postgresql+asyncpg://user:pass@localhost:5432/dbname",
        metrics_enabled=False,
    )
    with pytest.raises(ValueError, match="explicit 'CORS_ORIGINS'"):
        Settings(**base)

    monkeypatch.setenv("CORS_ORIGINS", "https://app.globaltalk.ai")
    prod = Settings(**base)
    assert prod.cors_origins == ["https://app.globaltalk.ai"]


def test_app_env_rejects_unknown_modes():
    """A typo such as 'Production' must fail closed instead of skipping the gates."""
    for bad in ("Production", "prod", "staging"):
        with pytest.raises(ValidationError):
            Settings(app_env=bad)


def test_cors_preflight_and_origin_validation(services_app_client):
    """CORS preflight requests must validate origin against allowed origins."""
    # Preflight from allowed local origin
    res = services_app_client.options(
        "/api/v1/translate",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        },
    )
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert res.headers.get("access-control-allow-credentials") == "true"

    # Preflight from unauthorized foreign origin must NOT reflect the origin
    res_unauth = services_app_client.options(
        "/api/v1/translate",
        headers={
            "Origin": "http://evil-attacker.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        },
    )
    assert res_unauth.headers.get("access-control-allow-origin") != "http://evil-attacker.com"


def test_zero_hardcoded_live_secrets_in_repo():
    """Automated security scan ensuring no active production API keys or tokens are checked into repo."""
    repo_root = Path(__file__).resolve().parents[1]

    # Regex patterns for sensitive credentials
    PATTERNS = [
        re.compile(r"sk-[a-zA-Z0-9]{32,}"),  # OpenAI live keys
        re.compile(r"sk-proj-[a-zA-Z0-9_\-]{40,}"),  # OpenAI project keys
        re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS Access Key IDs
        re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),  # Private Keys
    ]

    scanned_count = 0
    findings = []

    # Target configuration, documentation, and source files
    target_exts = {".py", ".env", ".example", ".json", ".yaml", ".yml", ".ts", ".tsx", ".md"}

    for path in repo_root.rglob("*"):
        # Skip vendor directories and virtualenvs
        parts = set(path.parts)
        if {".venv", "node_modules", ".git", ".pytest_cache", "dist", "build"} & parts:
            continue
        if path.is_file() and (path.suffix in target_exts or path.name.startswith(".env")):
            scanned_count += 1
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                for pat in PATTERNS:
                    match = pat.search(content)
                    if match:
                        findings.append(f"{path}: matched {pat.pattern}")
            except Exception:
                continue

    assert scanned_count > 50, f"Expected to scan repository files, scanned {scanned_count}"
    assert not findings, f"Found sensitive hardcoded secrets in repository: {findings}"

