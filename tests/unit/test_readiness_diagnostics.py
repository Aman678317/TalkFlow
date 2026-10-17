import pytest
from app.ai import ai


@pytest.mark.asyncio
async def test_ai_diagnostics_structure_and_safe_output():
    diag = await ai.diagnostics()
    assert isinstance(diag, dict)
    assert "status" in diag
    assert diag["status"] in ("ready", "degraded", "unavailable")
    assert "tasks" in diag
    assert "stt" in diag["tasks"]
    assert "mt" in diag["tasks"]
    assert "tts" in diag["tasks"]
    assert "language_pairs" in diag
    assert "ocr" in diag

    # Security check: Ensure no secrets or tokens are exposed
    diag_str = str(diag).lower()
    for forbidden in ("secret", "token", "password", "key_val", "bearer"):
        assert forbidden not in diag_str


def test_readiness_probe_includes_diagnostics(services_app_client):
    # Test with diagnostics parameter using services_app_client
    res = services_app_client.get("/ready?diagnostics=true")
    assert res.status_code == 200
    data = res.json()
    assert "ready" in data
    assert "diagnostics" in data
    assert data["diagnostics"]["status"] in ("ready", "degraded", "unavailable")


def test_system_diagnostics_endpoint(services_app_client):
    res = services_app_client.get("/api/v1/system/diagnostics")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "infrastructure" in data
    assert "ai" in data
    assert "ocr" in data["ai"]
