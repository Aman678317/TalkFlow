"""Phase 16: DevOps & Deployment Alignment Test Suite.

Verifies:
1. Docker Compose manifest syntax, inter-service dependency graph, volume references, and ports.
2. Kubernetes YAML multi-document validation, namespace scoping, ingress route mappings, and probe contracts.
3. Nginx reverse proxy configuration for WebSocket upgrade, security headers, and path dispatching.
4. Dockerfile build recipes consistency for API, Web, and background worker images.
5. Database URL normalization and driver reconciliation between Kubernetes secrets and Docker Compose.
"""
from __future__ import annotations

import os
from pathlib import Path
import pytest
import yaml

from app.db.session import _normalize_db_url

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKER_DIR = REPO_ROOT / "infrastructure" / "docker"
K8S_DIR = REPO_ROOT / "infrastructure" / "kubernetes"


def test_docker_compose_manifest_alignment():
    """Verify docker-compose.yml structure, dependencies, volume declarations, and ports."""
    compose_path = DOCKER_DIR / "docker-compose.yml"
    assert compose_path.exists(), "infrastructure/docker/docker-compose.yml missing"

    with open(compose_path, "r", encoding="utf-8") as f:
        compose = yaml.safe_load(f)

    assert compose.get("name") == "globaltalk"
    services = compose.get("services", {})
    assert "postgres" in services
    assert "redis" in services
    assert "api" in services
    assert "worker" in services
    assert "web" in services
    assert "prometheus" in services

    # Verify all declared named volumes exist
    declared_volumes = set(compose.get("volumes", {}).keys())
    assert {"pgdata", "miniodata", "model-cache"}.issubset(declared_volumes)

    # Verify api service contracts
    api = services["api"]
    assert "8000:8000" in api.get("ports", [])
    assert "postgres" in api.get("depends_on", {})
    assert "redis" in api.get("depends_on", {})
    assert api.get("healthcheck") is not None

    # Verify database URL uses asyncpg driver
    api_env = compose.get("x-api-env", {})
    db_url = api_env.get("DATABASE_URL", "")
    assert "postgresql+asyncpg://" in db_url
    assert api_env.get("METRICS_ENABLED") == "true"

    # Verify worker depends on api and databases
    worker = services["worker"]
    assert "api" in worker.get("depends_on", {})
    assert "postgres" in worker.get("depends_on", {})
    assert "redis" in worker.get("depends_on", {})

    # Verify web depends on api
    web = services["web"]
    assert "api" in web.get("depends_on", {})


def test_nginx_reverse_proxy_configuration():
    """Verify nginx.conf security headers, API route coverage, and WebSocket upgrades."""
    nginx_path = DOCKER_DIR / "nginx.conf"
    assert nginx_path.exists(), "infrastructure/docker/nginx.conf missing"

    content = nginx_path.read_text(encoding="utf-8")

    # Security headers
    assert "X-Content-Type-Options nosniff" in content
    assert "X-Frame-Options DENY" in content
    assert "Referrer-Policy no-referrer" in content

    # Reverse proxy paths
    assert "location /api/" in content
    assert "location /ws/" in content
    assert "location /health" in content
    assert "location /ready" in content
    assert "location /version" in content
    assert "location /metrics" in content
    assert "location /docs" in content
    assert "location /openapi.json" in content
    assert "location /v2/" in content
    assert "location /v3/" in content

    # WebSocket upgrade configuration
    assert 'Upgrade $http_upgrade' in content
    assert 'Connection "upgrade"' in content
    assert "proxy_pass http://api:8000;" in content


def test_kubernetes_manifests_alignment():
    """Verify Kubernetes manifests: Namespace, Secrets, ConfigMap, Deployments, and Ingress paths."""
    k8s_path = K8S_DIR / "globaltalk.yaml"
    assert k8s_path.exists(), "infrastructure/kubernetes/globaltalk.yaml missing"

    with open(k8s_path, "r", encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f))

    assert len(docs) >= 8

    kinds = {doc.get("kind"): doc for doc in docs if doc}
    assert "Namespace" in kinds
    assert "Secret" in kinds
    assert "ConfigMap" in kinds
    assert "Deployment" in kinds
    assert "Service" in kinds
    assert "Ingress" in kinds

    # Verify namespace isolation
    for doc in docs:
        if not doc or doc.get("kind") == "Namespace":
            continue
        assert doc.get("metadata", {}).get("namespace") == "globaltalk", (
            f"Resource {doc.get('kind')}/{doc.get('metadata', {}).get('name')} must be in 'globaltalk' namespace"
        )

    # Verify Secret contains normalized asyncpg database url
    secret = kinds["Secret"]
    db_url = secret.get("stringData", {}).get("DATABASE_URL", "")
    assert "postgresql+asyncpg://" in db_url

    # Verify Ingress routing encompasses all API and frontend endpoints
    ingress = kinds["Ingress"]
    paths = [p["path"] for p in ingress["spec"]["rules"][0]["http"]["paths"]]
    expected_paths = [
        "/api", "/v2", "/v3", "/ws", "/health", "/ready", "/version",
        "/metrics", "/docs", "/openapi.json", "/"
    ]
    for exp in expected_paths:
        assert exp in paths, f"Path {exp} missing from Kubernetes Ingress"

    # Verify API deployment readiness and liveness probes
    deployments = [d for d in docs if d and d.get("kind") == "Deployment"]
    api_deploy = next(d for d in deployments if d["metadata"]["name"] == "api")
    containers = api_deploy["spec"]["template"]["spec"]["containers"]
    api_container = containers[0]
    assert api_container["readinessProbe"]["httpGet"]["path"] == "/ready"
    assert api_container["livenessProbe"]["httpGet"]["path"] == "/health"
    assert api_container["ports"][0]["containerPort"] == 8000


def test_dockerfile_recipes_consistency():
    """Verify Dockerfiles exist, install requirements, and configure valid entrypoints."""
    # 1. Dockerfile.api
    df_api = DOCKER_DIR / "Dockerfile.api"
    assert df_api.exists()
    api_text = df_api.read_text(encoding="utf-8")
    assert "requirements.txt" in api_text
    assert "services/api/requirements.txt" in api_text
    assert "uvicorn" in api_text
    assert "HEALTHCHECK" in api_text

    # 2. Dockerfile.web
    df_web = DOCKER_DIR / "Dockerfile.web"
    assert df_web.exists()
    web_text = df_web.read_text(encoding="utf-8")
    assert "npm run build" in web_text
    assert "nginx.conf" in web_text
    assert "EXPOSE 80" in web_text

    # 3. Dockerfile.worker
    df_worker = DOCKER_DIR / "Dockerfile.worker"
    assert df_worker.exists()
    worker_text = df_worker.read_text(encoding="utf-8")
    assert "WORKER_KIND" in worker_text


def test_database_url_normalization_cross_platform():
    """Verify _normalize_db_url transparently maps both postgresql:// and postgresql+psycopg:// to postgresql+asyncpg://."""
    raw_pg = "postgresql://user:pass@host:5432/db"
    assert _normalize_db_url(raw_pg) == "postgresql+asyncpg://user:pass@host:5432/db"

    psycopg_pg = "postgresql+psycopg://user:pass@host:5432/db"
    assert _normalize_db_url(psycopg_pg) == "postgresql+asyncpg://user:pass@host:5432/db"

    asyncpg_pg = "postgresql+asyncpg://user:pass@host:5432/db"
    assert _normalize_db_url(asyncpg_pg) == asyncpg_pg

    sqlite_raw = "sqlite:///tmp/test.db"
    assert _normalize_db_url(sqlite_raw) == "sqlite+aiosqlite:///tmp/test.db"

